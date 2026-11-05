import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_language, current_user
from app.api.reviews import ReviewIn, record_reviews
from app.db import get_db
from app.examples import for_unit
from app.learner import known_unit_ids
from app.models import AppUser, Card, Exposure, Unit, WordFrequency
from app.packs import INSTALLED, get_pack
from app.packs.base import WORD
from app.reader import now

router = APIRouter(tags=["lookup"])


@router.get("/lookup")
def lookup(q: str, language: str | None = None, text_id: int | None = None, log: bool = False,
           db: Session = Depends(get_db), user: AppUser = Depends(current_user),
           active: str = Depends(current_language)):
    """Dictionary, readings, levels and the pack's own sections (zh: CC-CEDICT and
    character decompositions) for a word. An inflected form resolves to its lemma.

    With log=true (a tap in the reader), the lookup is recorded as an exposure, and
    if the word already has a meaning card, as an unscheduled failed review."""
    language = language or active
    if language not in INSTALLED:
        raise HTTPException(400, f"no language pack installed for {language!r}")
    pack = get_pack(language)
    q = pack.normalize(q.strip())
    if not q:
        raise HTTPException(400, "empty query")

    units = list(db.scalars(select(Unit).where(Unit.language == language, Unit.headword == q).order_by(Unit.id)))
    form = None
    if not units:
        toks = [t for t in pack.analyze(q) if t.kind == WORD]
        if len(toks) == 1 and toks[0].head != q:
            form, q = q, toks[0].head
            units = list(db.scalars(select(Unit).where(Unit.language == language, Unit.headword == q).order_by(Unit.id)))

    logged = None
    if log and units:
        unit = next((u for u in units if (u.extra or {}).get("primary_form")), units[0])
        db.add(Exposure(user_id=user.id, unit_id=unit.id, text_id=text_id, looked_up=True, seen_at=now()))
        card = db.scalar(select(Card).where(Card.user_id == user.id, Card.unit_id == unit.id, Card.facet == "meaning"))
        if card is not None and card.last_review is not None:
            record_reviews(db, user.id, [ReviewIn(id=str(uuid.uuid4()), card_id=card.id, rating=1,
                                                  reviewed_at=now(), source="reader_lookup", scheduled=False)])
            logged = "failed_review"
        else:
            db.commit()
            logged = "exposure"

    primary = next((u for u in units if (u.extra or {}).get("primary_form")), units[0]) if units else None
    freq = db.get(WordFrequency, (language, q))
    return {
        "query": q,
        "form": form,  # the inflected form that was tapped, when it differs from the lemma
        "language": language,
        "frequency": {"rank": freq.rank, "per_million": freq.per_million} if freq else None,
        "examples": for_unit(db, primary.id, known_unit_ids(db, user.id, language)) if primary else [],
        "units": [
            {"id": u.id, "reading": u.reading, "reading_display": pack.reading_display(u.reading),
             "traditional": u.traditional, "level_tags": u.level_tags, "frequency_rank": u.frequency_rank,
             "classifiers": (u.extra or {}).get("classifiers", []), "meanings": pack.meanings(db, u),
             "pos": (u.extra or {}).get("pos", [])}
            for u in units
        ],
        "logged": logged,
        **pack.lookup_extras(db, q),
    }
