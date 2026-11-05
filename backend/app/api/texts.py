from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_language, current_user
from app.db import get_db
from app.models import AppUser, Exposure, Text
from app.packs import INSTALLED, get_pack
from app.packs.base import WORD
from app.generator import generate
from app.jobs import enqueue_render
from app.llm.errors import DailyCapError, LlmError, NoModelError, PlanLimitError, SignInRequiredError
from app.reader import create_text, now, serialize_text

router = APIRouter(prefix="/texts", tags=["texts"])


class ImportIn(BaseModel):
    title: str = Field(max_length=256)
    body: str = Field(min_length=1, max_length=200_000)
    language: str | None = None  # the active language when omitted
    source_url: str | None = None


def _own_text(db: Session, user: AppUser, text_id: int) -> Text:
    text = db.get(Text, text_id)
    if text is None or text.user_id != user.id:
        raise HTTPException(404, "text not found")
    return text


@router.post("/import")
def import_text(body: ImportIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user),
                lang: str = Depends(current_language)):
    """Paste import. URL, EPUB and subtitle importers build on this (phase 1+).
    The response includes coverage, so the reader can say whether a text is readable."""
    language = body.language or lang
    if language not in INSTALLED:
        raise HTTPException(400, f"no language pack for {language!r}")
    text = create_text(db, user.id, language, body.title, body.body, "imported", body.source_url)
    enqueue_render(db, user.id, text.id)
    return serialize_text(db, user.id, text)


class GenerateIn(BaseModel):
    topic: str = Field(default="", max_length=200)
    genre: str = "story"
    length: str = "medium"
    targets: list[str] = Field(default_factory=list, max_length=5)


@router.post("/generate")
def generate_text(body: GenerateIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user),
                  lang: str = Depends(current_language)):
    """A level-matched text from the model, checked against your known words.
    Takes 10-60 s with a ChatGPT plan; a background job comes with the worker."""
    try:
        text = generate(db, user.id, body.topic, body.genre, body.length, body.targets, lang)
    except (SignInRequiredError, NoModelError) as e:
        raise HTTPException(409, str(e))
    except (PlanLimitError, DailyCapError) as e:
        raise HTTPException(429, str(e))
    except LlmError as e:
        raise HTTPException(502, str(e))
    return serialize_text(db, user.id, text)


class FlagIn(BaseModel):
    sentence: int = Field(ge=0)
    note: str = Field(default="", max_length=500)


@router.post("/{text_id}/flag")
def flag_sentence(text_id: int, body: FlagIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """'Sounds unnatural': kept with the text so flagged sentences are never reused."""
    text = _own_text(db, user, text_id)
    meta = dict(text.meta or {})
    flags = [f for f in meta.get("flags", []) if f.get("sentence") != body.sentence]
    flags.append({"sentence": body.sentence, "note": body.note, "at": now().isoformat()})
    meta["flags"] = flags
    text.meta = meta
    db.commit()
    return {"flags": flags}


@router.get("")
def list_texts(db: Session = Depends(get_db), user: AppUser = Depends(current_user),
               lang: str = Depends(current_language)):
    rows = db.scalars(select(Text).where(Text.user_id == user.id, Text.language == lang)
                      .order_by(Text.created_at.desc()))
    return [
        {"id": t.id, "title": t.title, "provenance": t.provenance, "coverage_at_creation": t.coverage_at_creation,
         "created_at": t.created_at, "finished_at": t.finished_at}
        for t in rows
    ]


@router.get("/{text_id}")
def get_text(text_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    return serialize_text(db, user.id, _own_text(db, user, text_id))


@router.post("/{text_id}/finish")
def finish_text(text_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """'Finished' logs an exposure for every word: weak evidence, never a review."""
    text = _own_text(db, user, text_id)
    ts = now()
    unit_ids = {t.unit_id for t in text.tokens if t.kind == WORD and t.unit_id}
    for u in unit_ids:
        db.add(Exposure(user_id=user.id, unit_id=u, text_id=text.id, looked_up=False, seen_at=ts))
    text.finished_at = ts
    db.commit()
    pack = get_pack(text.language)
    words = [t.surface for t in text.tokens if t.kind == WORD]
    read = sum(len(w) for w in words) if pack.script_unit == "characters" else len(words)
    return {"exposures": len(unit_ids), "read": read, "read_unit": pack.script_unit}
