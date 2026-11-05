import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.reviews import ReviewIn, record_reviews
from app.db import get_db
from app.examples import for_unit
from app.learner import known_unit_ids
from app.models import AppUser, Card, CedictEntry, CharacterInfo, Exposure, Unit, WordFrequency
from app.packs import get_pack
from app.packs.zh.pinyin import apply_sandhi, numeric_to_marks
from app.reader import now

router = APIRouter(tags=["lookup"])


def _zh_reading(pack, word: str) -> dict:
    cite = pack.citation(word)
    surf = apply_sandhi([(word, cite)])[0]
    return {
        "citation": " ".join(cite),
        "citation_display": " ".join(numeric_to_marks(s) for s in cite),
        "surface_display": " ".join(numeric_to_marks(s) for s in surf),
    }


@router.get("/lookup")
def lookup(q: str, language: str = "zh", text_id: int | None = None, log: bool = False,
           db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Dictionary, readings, HSK levels and character decompositions for a word.

    With log=true (a tap in the reader), the lookup is recorded as an exposure, and
    if the word already has a meaning card, as an unscheduled failed review."""
    if language != "zh":
        raise HTTPException(400, "only the zh pack is installed")
    pack = get_pack(language)
    q = q.strip()
    if not q:
        raise HTTPException(400, "empty query")

    units = list(db.scalars(select(Unit).where(Unit.language == language, Unit.headword == q).order_by(Unit.id)))
    cedict = list(db.scalars(select(CedictEntry).where(CedictEntry.simplified == q)))
    chars = {c.character: c for c in db.scalars(select(CharacterInfo).where(CharacterInfo.character.in_(set(q))))}

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
    freq = db.get(WordFrequency, q)
    return {
        "query": q,
        "frequency": {"rank": freq.rank, "per_million": freq.per_million} if freq else None,
        "examples": for_unit(db, primary.id, known_unit_ids(db, user.id, language)) if primary else [],
        "reading": _zh_reading(pack, q),
        "units": [
            {"id": u.id, "reading": u.reading, "reading_display": " ".join(numeric_to_marks(s) for s in u.reading.split()),
             "traditional": u.traditional, "level_tags": u.level_tags, "frequency_rank": u.frequency_rank,
             "classifiers": (u.extra or {}).get("classifiers", []), "meanings": (u.extra or {}).get("meanings", []),
             "pos": (u.extra or {}).get("pos", [])}
            for u in units
        ],
        "cedict": [
            {"traditional": e.traditional, "pinyin": e.pinyin,
             "pinyin_display": " ".join(numeric_to_marks(s) for s in e.pinyin.replace("u:", "v").split()),
             "glosses": e.glosses}
            for e in cedict
        ],
        "characters": [
            {"character": ch, "definition": chars[ch].definition, "pinyin": chars[ch].pinyin,
             "decomposition": chars[ch].decomposition, "radical": chars[ch].radical,
             "etymology": chars[ch].etymology} if ch in chars else {"character": ch}
            for ch in pack.sub_units(q)
        ],
        "attribution": "CC-CEDICT (CC BY-SA 4.0); Make Me a Hanzi; complete-hsk-vocabulary (MIT); SUBTLEX-CH; Tatoeba (CC BY 2.0 FR)",
        "logged": logged,
    }
