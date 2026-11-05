"""Pre-teaching: before a hard imported text, read a short easy one that uses its
most useful unfamiliar words (design doc: LLM features -> pre-teaching texts)."""

from collections import Counter

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs as queue
from app.api.deps import current_user
from app.api.jobs import _require_model, _run_inline
from app.config import get_settings
from app.db import get_db
from app.models import AppUser, Text, Unit
from app.packs.base import WORD
from app.reader import unit_statuses

router = APIRouter(tags=["pre-teach"])
MAX_WORDS = 5


def hardest_words(db: Session, user_id: int, text: Text) -> tuple[list[str], int]:
    """Unfamiliar words worth learning first: most frequent in this text, then most
    common in general. Returns (words, number of distinct unfamiliar words)."""
    tokens = [t for t in text.tokens if t.kind == WORD and t.unit_id]
    statuses = unit_statuses(db, user_id, text.language, {t.unit_id for t in tokens})
    counts = Counter(t.unit_id for t in tokens if statuses.get(t.unit_id) == "new")
    if not counts:
        return [], 0
    units = {u.id: u for u in db.scalars(select(Unit).where(Unit.id.in_(counts)))}
    ranked = sorted(counts, key=lambda uid: (-counts[uid], units[uid].frequency_rank or 10**8))
    words = [units[u].headword for u in ranked if len(units[u].headword) <= 4][:MAX_WORDS]
    return words, len(counts)


def _own(db: Session, user: AppUser, text_id: int) -> Text:
    text = db.get(Text, text_id)
    if text is None or text.user_id != user.id:
        raise HTTPException(404, "text not found")
    return text


@router.get("/texts/{text_id}/pre-teach")
def suggestion(text_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    text = _own(db, user, text_id)
    words, unknown = hardest_words(db, user.id, text)
    return {"words": words, "unknown": unknown, "existing": (text.meta or {}).get("pre_teach")}


@router.post("/texts/{text_id}/pre-teach", status_code=202)
def pre_teach(text_id: int, tasks: BackgroundTasks, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Queue a short warm-up text built around the text's most useful new words."""
    text = _own(db, user, text_id)
    words, _ = hardest_words(db, user.id, text)
    if not words:
        raise HTTPException(409, "You already know every word here.")
    _require_model(db)
    job = queue.enqueue(db, user.id, "generate", {
        "topic": f"something related to: {text.title}", "genre": "story", "length": "short",
        "targets": words, "pre_teach_for": text.id})
    if get_settings().inline_jobs:
        tasks.add_task(_run_inline)
    return {"job_id": job.id, "words": words}
