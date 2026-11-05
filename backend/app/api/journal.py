from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs as queue
from app.api.deps import current_language, current_user
from app.api.jobs import _require_model, _run_inline
from app.config import get_settings
from app.db import get_db
from app.journal import categories, category_counts, writing_prompt
from app.models import AppUser, ErrorItem, JournalEntry

router = APIRouter(prefix="/journal", tags=["journal"])


def _entry(db: Session, e: JournalEntry) -> dict:
    errors = list(db.scalars(select(ErrorItem).where(ErrorItem.entry_id == e.id).order_by(ErrorItem.id)))
    labels = categories(e.language or "zh")
    return {
        "id": e.id, "text": e.text, "status": e.status, "corrected": e.corrected, "comment": e.comment,
        "error": e.error, "prompt": e.prompt, "created_at": e.created_at, "sentences": e.sentences,
        "language": e.language,
        "errors": [{"id": x.id, "category": x.category, "label": labels.get(x.category, x.category),
                    "wrong": x.wrong, "right": x.right, "explanation": x.explanation,
                    "sentence_index": x.sentence_index, "card_id": x.card_id} for x in errors],
    }


@router.get("/prompt")
def prompt(db: Session = Depends(get_db), user: AppUser = Depends(current_user),
           lang: str = Depends(current_language)):
    return writing_prompt(db, user.id, lang)


class EntryIn(BaseModel):
    text: str = Field(min_length=2, max_length=1000)
    prompt: dict = Field(default_factory=dict)


@router.post("", status_code=202)
def write(body: EntryIn, tasks: BackgroundTasks, db: Session = Depends(get_db), user: AppUser = Depends(current_user),
          lang: str = Depends(current_language)):
    """Save an entry and queue its correction; poll GET /journal/{id}."""
    _require_model(db)
    entry = JournalEntry(user_id=user.id, language=lang, text=body.text.strip(), prompt=body.prompt, status="queued")
    db.add(entry)
    db.commit()
    queue.enqueue(db, user.id, "journal", {"entry_id": entry.id})
    if get_settings().inline_jobs:
        tasks.add_task(_run_inline)
    return _entry(db, entry)


@router.get("")
def entries(db: Session = Depends(get_db), user: AppUser = Depends(current_user),
            lang: str = Depends(current_language)):
    rows = db.scalars(select(JournalEntry).where(JournalEntry.user_id == user.id, JournalEntry.source == "journal",
                                                 JournalEntry.language == lang)
                      .order_by(JournalEntry.created_at.desc()).limit(30))
    return {"entries": [_entry(db, e) for e in rows], "categories": category_counts(db, user.id, language=lang),
            "labels": categories(lang)}


@router.get("/{entry_id}")
def entry(entry_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    e = db.get(JournalEntry, entry_id)
    if e is None or e.user_id != user.id:
        raise HTTPException(404, "entry not found")
    return _entry(db, e)


@router.post("/{entry_id}/retry", status_code=202)
def retry(entry_id: int, tasks: BackgroundTasks, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    e = db.get(JournalEntry, entry_id)
    if e is None or e.user_id != user.id:
        raise HTTPException(404, "entry not found")
    if e.status != "failed":
        raise HTTPException(409, "only failed entries can be retried")
    _require_model(db)
    e.status, e.error = "queued", None
    db.commit()
    queue.enqueue(db, user.id, "journal", {"entry_id": e.id})
    if get_settings().inline_jobs:
        tasks.add_task(_run_inline)
    return _entry(db, e)
