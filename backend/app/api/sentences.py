from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.examples import _units_by_sentence, for_unit, serialize, tatoeba_url
from app.learner import known_unit_ids
from app.models import AppUser, Card, ExampleSentence, SentenceUnit, Text
from app.reader import create_text, sentence_map, serialize_text

router = APIRouter(tags=["sentences"])

TERMINATORS = "。！？!?…”」"


@router.get("/units/{unit_id}/examples")
def examples(unit_id: int, limit: int = 3, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Human-written sentences for a word, the ones you can read best first."""
    return for_unit(db, unit_id, known_unit_ids(db, user.id, "zh"), max(1, min(limit, 10)))


class SentencesIn(BaseModel):
    n: int = Field(default=8, ge=3, le=20)


@router.post("/texts/sentences")
def sentences_text(body: SentencesIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """A reading text of real sentences at your level: at most one unknown word
    each, preferring sentences that use words you're learning. Never repeats a
    sentence from an earlier one of these texts."""
    known = known_unit_ids(db, user.id, "zh")
    learning = set(db.scalars(select(Card.unit_id).where(Card.user_id == user.id))) - known
    used = {i for meta in db.scalars(select(Text.meta).where(Text.user_id == user.id, Text.provenance == "tatoeba"))
            for i in (meta or {}).get("sentence_ids", [])}

    def candidates(q, limit):
        return [s for s in db.scalars(q.order_by(ExampleSentence.difficulty, ExampleSentence.n_words).limit(limit))
                if s.id not in used]

    pool = []
    if learning:
        pool += candidates(select(ExampleSentence).join(SentenceUnit, SentenceUnit.sentence_id == ExampleSentence.id)
                           .where(SentenceUnit.unit_id.in_(learning)).distinct(), 3000)
    pool += candidates(select(ExampleSentence), 3000)
    if not pool:
        if db.scalar(select(ExampleSentence.id).limit(1)) is None:
            raise HTTPException(409, "No example sentences imported yet. Run ops/import-data.sh with the Tatoeba files.")
        raise HTTPException(409, "You've read every imported sentence in these texts. Import a newer Tatoeba export for more.")
    linked = _units_by_sentence(db, list({s.id for s in pool}))
    readable = known | learning

    def unknown(s: ExampleSentence) -> int:
        return s.n_words - len(linked[s.id] & readable)

    chosen, seen = [], set()
    # Learning-word sentences first, then any; tighten to <=1 unknown word, relaxing
    # for beginners who don't know enough words yet.
    for limit in (1, 2, 99):
        for s in pool:
            if len(chosen) >= body.n:
                break
            if s.id not in seen and unknown(s) <= limit:
                chosen.append(s)
                seen.add(s.id)
        if len(chosen) >= body.n:
            break
    zh = [s.text if s.text[-1] in TERMINATORS else s.text + "。" for s in chosen]
    text = create_text(db, user.id, "zh", f"例句 · Sentences {date.today():%b %d}", "".join(zh), provenance="tatoeba")
    text.meta = {
        "sentences": [{"zh": z, "en": s.translation, "id": s.id, "url": tatoeba_url(s.id)} for z, s in zip(zh, chosen)],
        "sentence_map": sentence_map(zh),
        "sentence_ids": [s.id for s in chosen],
        "attribution": "Sentences from Tatoeba (tatoeba.org), CC BY 2.0 FR",
    }
    db.commit()
    return serialize_text(db, user.id, text)
