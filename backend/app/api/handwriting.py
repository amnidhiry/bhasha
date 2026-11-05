from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.learner import retrievability, user_scheduler
from app.models import AppUser, Card, CharacterStrokes, Unit
from app.reader import now
from app.units import ensure_character

router = APIRouter(tags=["handwriting"])

BANDS = ["1-2", "3", "4", "5", "6", "7-9"]
WRITTEN = 0.9  # recall probability at which a character counts as writable


@router.get("/hanzi/{char}")
def strokes(char: str, db: Session = Depends(get_db)):
    """Stroke data in Hanzi Writer's format (Make Me a Hanzi graphics). Immutable,
    so the browser and service worker cache it for offline practice."""
    row = db.get(CharacterStrokes, char)
    if row is None or len(char) != 1:
        raise HTTPException(404, "no stroke data for this character")
    return JSONResponse({"strokes": row.strokes, "medians": row.medians},
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


def _hw_cards(db: Session, user_id: int) -> dict[int, Card]:
    return {c.unit_id: c for c in db.scalars(select(Card).where(Card.user_id == user_id, Card.facet == "handwriting"))}


@router.get("/handwriting")
def overview(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Progress through the official HSK 3.0 handwriting list, by band."""
    cards = _hw_cards(db, user.id)
    t = now()
    sched = user_scheduler(db, user.id)
    units = list(db.scalars(select(Unit).where(Unit.language == "zh", Unit.type == "character")))
    out = []
    for band in BANDS:
        tag = f"hw2025:{band}"
        in_band = [u for u in units if tag in (u.level_tags or [])]
        practising = [u for u in in_band if u.id in cards]
        written = [u for u in practising
                   if cards[u.id].state == 2 and retrievability(cards[u.id], t, sched) >= WRITTEN]
        out.append({"band": band, "total": len(in_band), "practising": len(practising), "written": len(written)})
    listed = {u.id for u in units if any(tag.startswith("hw2025:") for tag in (u.level_tags or []))}
    extra = sum(1 for uid in cards if uid not in listed)
    return {"bands": out, "own_characters": extra, "cards": len(cards)}


class AddIn(BaseModel):
    characters: list[str] = Field(default_factory=list, max_length=50)
    from_list: int = Field(default=0, ge=0, le=50, description="add the next N from the official list")
    context: str | None = Field(default=None, max_length=200)


@router.post("/handwriting/add")
def add(body: AddIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Start handwriting cards: specific characters (e.g. from a word you looked
    up), or the next N of the official list in order."""
    cards = _hw_cards(db, user.id)
    targets: list[Unit] = []
    for ch in dict.fromkeys(c for c in "".join(body.characters) if "\u3400" <= c <= "\u9fff"):
        if db.get(CharacterStrokes, ch) is None:
            continue
        targets.append(ensure_character(db, ch))
    if body.from_list:
        listed = sorted(
            (u for u in db.scalars(select(Unit).where(Unit.language == "zh", Unit.type == "character"))
             if any(t.startswith("hw2025:") for t in (u.level_tags or [])) and u.id not in cards),
            key=lambda u: (u.extra or {}).get("hw_order", 10**9),
        )
        targets += listed[: body.from_list]
    created = []
    for u in targets:
        if u.id in cards:
            continue
        card = Card(user_id=user.id, unit_id=u.id, facet="handwriting", due=now(), context_sentence=body.context)
        db.add(card)
        db.flush()
        cards[u.id] = card
        created.append({"card_id": card.id, "character": u.headword})
    db.commit()
    return {"created": created}
