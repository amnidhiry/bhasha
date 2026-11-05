"""Pick human-written example sentences a learner can actually read."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExampleSentence, SentenceUnit

CANDIDATES = 200  # easiest sentences considered per word before ranking by your coverage


def tatoeba_url(sid: int) -> str:
    return f"https://tatoeba.org/en/sentences/show/{sid}"


def _units_by_sentence(db: Session, ids: list[int]) -> dict[int, set[int]]:
    out: dict[int, set[int]] = {i: set() for i in ids}
    for sid, uid in db.execute(select(SentenceUnit.sentence_id, SentenceUnit.unit_id).where(SentenceUnit.sentence_id.in_(ids))):
        out[sid].add(uid)
    return out


def score(s: ExampleSentence, linked: set[int], known: set[int], focus: int | None = None) -> float:
    """Share of the sentence's words you know (the focus word counts as known)."""
    known_words = len((linked & known) | ({focus} & linked if focus else set()))
    return known_words / max(1, s.n_words)


def for_unit(db: Session, unit_id: int, known: set[int], limit: int = 3) -> list[dict]:
    rows = list(db.scalars(
        select(ExampleSentence).join(SentenceUnit, SentenceUnit.sentence_id == ExampleSentence.id)
        .where(SentenceUnit.unit_id == unit_id).order_by(ExampleSentence.difficulty, ExampleSentence.n_words)
        .limit(CANDIDATES)
    ))
    if not rows:
        return []
    linked = _units_by_sentence(db, [s.id for s in rows])
    ranked = sorted(rows, key=lambda s: (-score(s, linked[s.id], known, unit_id), s.n_words))
    return [serialize(s, score(s, linked[s.id], known, unit_id)) for s in ranked[:limit]]


def serialize(s: ExampleSentence, coverage: float | None = None) -> dict:
    return {"id": s.id, "text": s.text, "translation": s.translation, "coverage": coverage,
            "source": s.source, "url": tatoeba_url(s.id)}
