from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func, literal, select
from sqlalchemy.orm import Session

from app.api.deps import current_language, current_user
from app.db import get_db
from app.learner import known_unit_ids
from app.models import AppUser, Card, Text, TextToken, Unit
from app.packs import get_pack
from app.packs.base import WORD

router = APIRouter(tags=["progress"])


@router.get("/progress")
def progress(language: str | None = None, db: Session = Depends(get_db), user: AppUser = Depends(current_user),
             active: str = Depends(current_language)):
    """Honest metrics: known words (and characters), coverage by level of the pack's
    framework (HSK 3.0 for zh), reading volume. No streaks."""
    language = language or active
    pack = get_pack(language)
    fw = pack.levels
    version = fw.tag_prefix
    known = known_unit_ids(db, user.id, language)
    words = list(db.scalars(select(Unit).where(Unit.language == language, Unit.type == "word")))
    known_heads = {u.headword for u in words if u.id in known}

    # Per-headword, since HSK level tags are per headword, not per reading.
    level_heads: dict[str, set[str]] = defaultdict(set)
    for u in words:
        for tag in u.level_tags or []:
            v, _, lvl = tag.partition(":")
            if v == version:
                level_heads[lvl].add(u.headword)
    levels = []
    cumulative: set[str] = set()
    order = {lvl: i for i, lvl in enumerate(fw.levels)}
    for lvl in sorted(level_heads, key=lambda x: order.get(x, len(order))):
        cumulative |= level_heads[lvl]
        k = len(cumulative & known_heads)
        levels.append({"level": lvl, "label": fw.label(lvl), "words": len(cumulative), "known": k,
                       "coverage": k / len(cumulative) if cumulative else None})

    finished = db.scalar(select(func.count()).select_from(Text).where(
        Text.user_id == user.id, Text.language == language, Text.finished_at.is_not(None))) or 0
    # Reading volume as learners count it: characters for zh, words otherwise.
    size = func.length(TextToken.surface) if pack.script_unit == "characters" else literal(1)
    read = db.scalar(
        select(func.coalesce(func.sum(size), 0)).select_from(TextToken)
        .join(Text, Text.id == TextToken.text_id)
        .where(Text.user_id == user.id, Text.language == language, Text.finished_at.is_not(None),
               TextToken.kind == WORD)
    ) or 0
    cards = db.scalar(select(func.count()).select_from(Card).join(Unit, Card.unit_id == Unit.id)
                      .where(Card.user_id == user.id, Unit.language == language)) or 0
    out = {
        "language": language,
        "known_words": len(known_heads),
        "cards": cards,
        "framework": fw.name,
        "level_version": version,
        "level_cumulative": levels,
        "texts_finished": finished,
        "read": read,
        "read_unit": pack.script_unit,
    }
    if "characters" in pack.features:
        out["known_characters"] = len({ch for h in known_heads for ch in pack.sub_units(h)})
    return out
