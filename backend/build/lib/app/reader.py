"""Text pipeline: analyze with the language pack, resolve tokens to units,
compute coverage against the learner model, and serialize for the reader."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner import coverage, ignored_unit_ids, known_unit_ids
from app.models import Card, Text, TextToken, Unit
from app.packs import get_pack
from app.packs.base import WORD, Token

NEW, LEARNING, KNOWN, IGNORED = "new", "learning", "known", "ignored"


def resolve_units(db: Session, language: str, tokens: list[Token]) -> list[int | None]:
    """Map word tokens to word units, preferring the reading that matches the
    pack's context-aware reading. Unseen words get a unit so they can be mined."""
    pack = get_pack(language)
    words = {t.surface for t in tokens if t.kind == WORD}
    by_head: dict[str, list[Unit]] = {}
    if words:
        for u in db.scalars(
            select(Unit).where(Unit.language == language, Unit.type == "word", Unit.headword.in_(words)).order_by(Unit.id)
        ):
            by_head.setdefault(u.headword, []).append(u)

    out: list[int | None] = []
    for t in tokens:
        if t.kind != WORD:
            out.append(None)
            continue
        reading = " ".join(s.citation for s in t.syllables) or pack.reading(t.surface)
        cands = by_head.get(t.surface, [])
        unit = next((u for u in cands if u.reading == reading), None)
        if unit is None:
            unit = next((u for u in cands if (u.extra or {}).get("primary_form")), None) or (cands[0] if cands else None)
        if unit is None:
            unit = Unit(language=language, type="word", headword=t.surface, reading=reading,
                        extra={"source": "segmenter"})
            db.add(unit)
            db.flush()
            by_head[t.surface] = [unit]
        out.append(unit.id)
    return out


def create_text(db: Session, user_id: int, language: str, title: str, body: str,
                provenance: str = "imported", source_url: str | None = None) -> Text:
    tokens = get_pack(language).analyze(body)
    unit_ids = resolve_units(db, language, tokens)
    known = known_unit_ids(db, user_id, language)
    cov = coverage([u for t, u in zip(tokens, unit_ids) if t.kind == WORD], known, ignored_unit_ids(db, user_id))
    text = Text(user_id=user_id, language=language, title=title, body=body, provenance=provenance,
                source_url=source_url, coverage_at_creation=cov)
    text.tokens = [
        TextToken(position=i, sentence_index=t.sentence_index, surface=t.surface, kind=t.kind, unit_id=u)
        for i, (t, u) in enumerate(zip(tokens, unit_ids))
    ]
    db.add(text)
    db.commit()
    return text


def unit_statuses(db: Session, user_id: int, language: str, unit_ids: set[int]) -> dict[int, str]:
    known = known_unit_ids(db, user_id, language)
    ignored = ignored_unit_ids(db, user_id)
    carded = set(db.scalars(select(Card.unit_id).where(Card.user_id == user_id, Card.unit_id.in_(unit_ids))))
    out = {}
    for u in unit_ids:
        out[u] = IGNORED if u in ignored else KNOWN if u in known else LEARNING if u in carded else NEW
    return out


def serialize_text(db: Session, user_id: int, text: Text) -> dict:
    """Tokens with status and reading aids. Pinyin is recomputed (cheap) rather
    than stored, so sandhi or reading fixes apply to old texts too."""
    analyzed = get_pack(text.language).analyze(text.body)
    surfaces_match = [a.surface for a in analyzed] == [t.surface for t in text.tokens]
    statuses = unit_statuses(db, user_id, text.language, {t.unit_id for t in text.tokens if t.unit_id})
    eligible = [t.unit_id for t in text.tokens if t.kind == WORD]
    known = {u for u, s in statuses.items() if s == KNOWN}
    ignored = {u for u, s in statuses.items() if s == IGNORED}
    tokens = []
    for i, tok in enumerate(text.tokens):
        status = statuses.get(tok.unit_id) if tok.unit_id else None
        syllables = analyzed[i].syllables if surfaces_match else []
        tokens.append({
            "position": tok.position,
            "sentence_index": tok.sentence_index,
            "surface": tok.surface,
            "kind": tok.kind,
            "unit_id": tok.unit_id,
            "status": status,
            "show_reading": status in (NEW, LEARNING),
            "syllables": [s.__dict__ for s in syllables],
        })
    return {
        "id": text.id,
        "title": text.title,
        "language": text.language,
        "provenance": text.provenance,
        "source_url": text.source_url,
        "coverage_at_creation": text.coverage_at_creation,
        "coverage_now": coverage(eligible, known, ignored),
        "finished_at": text.finished_at,
        "tokens": tokens,
    }


def now() -> datetime:
    return datetime.now(timezone.utc)
