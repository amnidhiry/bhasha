from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Unit
from app.packs.zh.pinyin import citation_syllables


def ensure_character(db: Session, ch: str) -> Unit:
    """The character unit for `ch`, created on first use with its most common reading."""
    unit = db.scalar(select(Unit).where(Unit.language == "zh", Unit.type == "character", Unit.headword == ch))
    if unit is None:
        # Meanings are looked up when a card is shown (Make Me a Hanzi may be imported later).
        unit = Unit(language="zh", type="character", headword=ch, reading=citation_syllables(ch)[0],
                    level_tags=[], track_tags=[], extra={})
        db.add(unit)
        db.flush()
    return unit
