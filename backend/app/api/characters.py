"""Characters module: character pages, the component explorer and the overview
of the learner's characters. See app/characters.py for the index and the
opaque-character notes."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.characters import (
    char_summary, character_status, family, family_info, get_index, productive_groups, rank_key, readings_of,
    short_gloss,
)
from app.config import get_settings
from app.db import get_db
from app.learner import known_unit_ids
from app.models import AppUser, Card, CharacterStrokes, Unit
from app.packs.zh.pinyin import numeric_to_marks

router = APIRouter(tags=["characters"])

ATTRIBUTION = "Make Me a Hanzi (decompositions, etymology); SUBTLEX-CH (frequency)"


@router.get("/characters")
def overview(groups: int = 12, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """The characters the learner knows or is learning, plus the components that
    appear in most of them (a way into the explorer)."""
    idx = get_index(db)
    status = character_status(db, user.id)
    mine = sorted(status, key=rank_key(idx, status))
    return {
        "counts": {"known": sum(1 for s in status.values() if s == "known"),
                   "learning": sum(1 for s in status.values() if s == "learning")},
        "characters": [char_summary(idx, ch, status) for ch in mine],
        "groups": productive_groups(idx, mine, limit=max(1, min(groups, 40))),
        "attribution": ATTRIBUTION,
    }


@router.get("/components/{component}")
def explore(component: str, direct: bool = False, all: bool = False, limit: int = 300,
            db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Characters containing a component (any variant form: 氵 finds 水 too, and
    parts of parts count, so 月 finds 清 through 青). Known first, then learning,
    then by frequency. Rare and traditional-only characters (no frequency data)
    are left out unless all=true, or they're the learner's own."""
    if len(component) != 1:
        raise HTTPException(400, "one component at a time")
    idx = get_index(db)
    key = family(component)
    if key not in idx.by_family and component not in idx.chars:
        raise HTTPException(404, "not a known component")
    status = character_status(db, user.id)
    has_freq = bool(idx.freq)
    found = []
    for ch in idx.by_family.get(key, []):
        depth, via = idx.chars[ch].contains[key]
        if direct and depth > 1:
            continue
        if not all and has_freq and ch not in status and ch not in idx.freq:
            continue
        found.append((ch, depth, via))
    found.sort(key=lambda t: rank_key(idx, status)(t[0]))
    total = len(found)
    out = []
    for ch, depth, via in found[: max(1, min(limit, 2000))]:
        out.append({**char_summary(idx, ch, status), "depth": depth, "via": via if depth > 1 else None})
    info = family_info(idx, key)
    return {
        "component": component,
        "family": info,
        "counts": {"total": total,
                   "known": sum(1 for ch, _, _ in found if status.get(ch) == "known"),
                   "learning": sum(1 for ch, _, _ in found if status.get(ch) == "learning")},
        "characters": out,
        "filtered": not all and has_freq,
        "attribution": ATTRIBUTION,
    }


@router.get("/characters/{char}")
def character(char: str, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Everything about one character: decomposition with each part's meaning and
    role, etymology, readings, frequency, the learner's words that contain it, and
    notes on whether its parts help (opaque-character warnings)."""
    if len(char) != 1:
        raise HTTPException(400, "one character at a time")
    idx = get_index(db)
    e = idx.chars.get(char)
    if e is None:
        raise HTTPException(404, "no Make Me a Hanzi entry for this character")
    status = character_status(db, user.id)
    ety = e.etymology or {}

    part_rows = []
    for p in e.parts:
        pe = idx.chars.get(p)
        role = "meaning" if p == ety.get("semantic") else "sound" if p == ety.get("phonetic") else None
        key = family(p)
        same_family = [ch for ch in idx.by_family.get(key, []) if ch in status and ch != char]
        part_rows.append({
            "component": p, "family": key, "members": family_info(idx, key)["members"],
            "definition": pe.definition if pe else None, "gloss": short_gloss(pe.definition if pe else None),
            "pinyin": readings_of(idx, p), "role": role,
            "decomposition": pe.decomposition if pe and len(pe.parts) > 1 else None,
            "yours": len(same_family),
        })

    # The learner's words with this character: known first, then the ones in review.
    known_ids = known_unit_ids(db, user.id, "zh")
    words = list(db.scalars(select(Unit).where(Unit.language == "zh", Unit.type == "word",
                                               Unit.headword.contains(char))))
    carded = set(db.scalars(select(Card.unit_id).where(
        Card.user_id == user.id, Card.unit_id.in_([u.id for u in words])))) if words else set()

    def word_row(u: Unit, st: str) -> dict:
        return {"unit_id": u.id, "headword": u.headword,
                "reading_display": " ".join(numeric_to_marks(s) for s in u.reading.split()),
                "meanings": (u.extra or {}).get("meanings", [])[:2], "status": st}

    yours, seen = [], set()
    for u in sorted(words, key=lambda u: (u.id not in known_ids, u.frequency_rank or 10**9, len(u.headword))):
        if u.headword in seen or (u.id not in known_ids and u.id not in carded):
            continue
        seen.add(u.headword)
        yours.append(word_row(u, "known" if u.id in known_ids else "learning"))
    version = get_settings().hsk_version
    suggestions = []
    for u in sorted(words, key=lambda u: (min((int(t.partition(":")[2]) for t in u.level_tags or []
                                                if t.startswith(version + ":") and t.partition(":")[2].isdigit()),
                                               default=99), u.frequency_rank or 10**9, len(u.headword))):
        if u.headword in seen or not any(t.startswith(version + ":") for t in u.level_tags or []):
            continue
        seen.add(u.headword)
        suggestions.append(word_row(u, "new"))
        if len(suggestions) >= 6:
            break

    hw = db.scalar(select(Card.id).join(Unit, Unit.id == Card.unit_id).where(
        Card.user_id == user.id, Card.facet == "handwriting", Unit.type == "character", Unit.headword == char))
    rank = idx.freq.get(char)
    return {
        **char_summary(idx, char, status),
        "decomposition": e.decomposition,
        "radical": e.radical,
        "radical_family": family(e.radical) if e.radical else None,
        "etymology": e.etymology,
        "parts": part_rows,
        "frequency": {"rank": rank[0], "per_million": round(rank[1], 2)} if rank else None,
        "notes": e.notes,
        "words": yours[:40],
        "more_words": suggestions,
        "has_strokes": db.get(CharacterStrokes, char) is not None,
        "writing": hw is not None,
        "attribution": ATTRIBUTION,
    }
