"""Drafts and their preview: coverage of a text before it is saved."""

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.importing.textutil import current, script_count
from app.learner import ignored_unit_ids, known_unit_ids
from app.packs import get_pack
from app.packs.base import WORD
from app.reader import resolve_units

# A text body is capped at this in the paste API; drafts follow suit.
MAX_BODY = 200_000


@dataclass
class Part:
    title: str
    body: str


@dataclass
class Draft:
    kind: str  # url | epub | subtitles | jellyfin
    title: str
    parts: list[Part]
    source_url: str | None = None
    meta: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def number_parts(title: str, bodies: list[str]) -> list[Part]:
    if len(bodies) == 1:
        return [Part(title, bodies[0])]
    return [Part(f"{title} ({i}/{len(bodies)})", b) for i, b in enumerate(bodies, 1)]


def _score(db: Session, user_id: int, language: str, body: str, known: set[int], ignored: set[int]) -> dict:
    """The same count `create_text` stores as coverage_at_creation, but words
    with no unit yet stay unknown instead of being created."""
    tokens = get_pack(language).analyze(body)
    unit_ids = resolve_units(db, language, tokens, create=False)
    eligible = [(t.surface, u) for t, u in zip(tokens, unit_ids) if t.kind == WORD and u not in ignored]
    known_n = sum(1 for _, u in eligible if u is not None and u in known)
    new_words = {s for s, u in eligible if u is None or u not in known}
    return {"eligible": len(eligible), "known": known_n, "new_words": new_words}


def preview(db: Session, user_id: int, draft: Draft, language: str | None = None) -> dict:
    language = language or current()
    known = known_unit_ids(db, user_id, language)
    ignored = ignored_unit_ids(db, user_id)
    parts, eligible, known_n, new_words = [], 0, 0, set()
    for p in draft.parts:
        s = _score(db, user_id, language, p.body, known, ignored)
        eligible += s["eligible"]
        known_n += s["known"]
        new_words |= s["new_words"]
        parts.append({
            "title": p.title,
            "body": p.body,
            "characters": script_count(p.body),
            "coverage": s["known"] / s["eligible"] if s["eligible"] else None,
            "new_words": len(s["new_words"]),
        })
    db.rollback()  # nothing should have been written; make sure of it
    return {
        "kind": draft.kind,
        "title": draft.title,
        "source_url": draft.source_url,
        "meta": draft.meta,
        "warnings": draft.warnings,
        "characters": sum(p["characters"] for p in parts),
        "coverage": known_n / eligible if eligible else None,
        "new_words": len(new_words),
        "parts": parts,
    }
