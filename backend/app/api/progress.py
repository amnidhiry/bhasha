from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import get_settings
from app.db import get_db
from app.learner import known_unit_ids
from app.models import AppUser, Card, Text, TextToken, Unit
from app.packs.base import WORD

router = APIRouter(tags=["progress"])


@router.get("/progress")
def progress(language: str = "zh", db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Honest metrics: known words and characters, HSK coverage by level, reading volume.
    No streaks."""
    version = get_settings().hsk_version
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
    for lvl in sorted(level_heads, key=int):
        cumulative |= level_heads[lvl]
        k = len(cumulative & known_heads)
        levels.append({"level": lvl, "words": len(cumulative), "known": k,
                       "coverage": k / len(cumulative) if cumulative else None})

    known_chars = {ch for h in known_heads for ch in h}
    finished = db.scalar(select(func.count()).select_from(Text).where(
        Text.user_id == user.id, Text.finished_at.is_not(None))) or 0
    chars_read = db.scalar(
        select(func.coalesce(func.sum(func.length(TextToken.surface)), 0))
        .join(Text, Text.id == TextToken.text_id)
        .where(Text.user_id == user.id, Text.finished_at.is_not(None), TextToken.kind == WORD)
    ) or 0
    cards = db.scalar(select(func.count()).select_from(Card).where(Card.user_id == user.id)) or 0
    return {
        "known_words": len(known_heads),
        "known_characters": len(known_chars),
        "cards": cards,
        "hsk_version": version,
        "hsk_cumulative": levels,
        "texts_finished": finished,
        "characters_read": chars_read,
    }
