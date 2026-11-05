from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.models import AppUser, Card, Text, Unit, UnitMark
from app.packs import get_pack
from app.reader import now

router = APIRouter(tags=["mining"])

ALLOWED_FACETS = {"meaning", "reading", "listening", "tone", "production", "cloze"}


class MineIn(BaseModel):
    unit_id: int
    sentence: str | None = None
    text_id: int | None = None
    facets: list[str] | None = None

    @model_validator(mode="after")
    def needs_context(self):
        # New words enter the queue only after you meet them in a text.
        if not self.sentence and self.text_id is None:
            raise ValueError("mining needs the sentence or text the word was met in")
        return self


@router.post("/mine")
def mine(body: MineIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    unit = db.get(Unit, body.unit_id)
    if unit is None:
        raise HTTPException(404, "unit not found")
    if body.text_id is not None:
        text = db.get(Text, body.text_id)
        if text is None or text.user_id != user.id:
            raise HTTPException(404, "text not found")
    facets = body.facets or list(get_pack(unit.language).default_facets)
    bad = set(facets) - ALLOWED_FACETS
    if bad:
        raise HTTPException(400, f"unknown facets: {sorted(bad)}")
    created = []
    for facet in facets:
        exists = db.scalar(select(Card).where(Card.user_id == user.id, Card.unit_id == unit.id, Card.facet == facet))
        if exists:
            continue
        card = Card(user_id=user.id, unit_id=unit.id, facet=facet, due=now(),
                    context_sentence=body.sentence, source_text_id=body.text_id)
        db.add(card)
        db.flush()
        created.append({"card_id": card.id, "facet": facet})
    db.commit()
    return {"unit_id": unit.id, "created": created}


class MarkIn(BaseModel):
    status: str  # known | ignored | clear
    unit_ids: list[int] = []
    level_tag: str | None = None  # e.g. "hsk3-2025:1" for placement bulk marks


@router.post("/units/mark")
def mark(body: MarkIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    if body.status not in ("known", "ignored", "clear"):
        raise HTTPException(400, "status must be known, ignored or clear")
    ids = set(body.unit_ids)
    if body.level_tag:
        for u in db.scalars(select(Unit).where(Unit.type == "word")):
            if body.level_tag in (u.level_tags or []):
                ids.add(u.id)
    for uid in ids:
        existing = db.get(UnitMark, (user.id, uid))
        if body.status == "clear":
            if existing:
                db.delete(existing)
        elif existing:
            existing.status = body.status
            existing.marked_at = now()
        else:
            db.add(UnitMark(user_id=user.id, unit_id=uid, status=body.status))
    db.commit()
    return {"marked": len(ids), "status": body.status}
