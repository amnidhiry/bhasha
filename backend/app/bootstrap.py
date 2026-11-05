from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppUser, Language, Unit
from app.packs import INSTALLED, get_pack

DEFAULT_USER = "me"


def ensure_defaults(db: Session) -> None:
    for code, name in INSTALLED.items():
        if db.get(Language, code) is None:
            db.add(Language(code=code, name=name))
    if db.scalar(select(AppUser).where(AppUser.name == DEFAULT_USER)) is None:
        db.add(AppUser(name=DEFAULT_USER))
    db.commit()


def warm_packs(db: Session) -> None:
    """Load curriculum and mined words into each pack's tokenizer dictionary."""
    for code in INSTALLED:
        rows = db.execute(select(Unit.headword, Unit.reading).where(Unit.language == code, Unit.type == "word"))
        get_pack(code).add_words((h, r) for h, r in rows)
