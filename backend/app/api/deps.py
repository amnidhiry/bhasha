from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bootstrap import DEFAULT_USER
from app.db import get_db
from app.models import AppUser


def current_user(db: Session = Depends(get_db)) -> AppUser:
    """Single-user for now. This is the seam for real auth (family use): every
    query below already filters by user_id."""
    user = db.scalar(select(AppUser).where(AppUser.name == DEFAULT_USER))
    if user is None:
        raise HTTPException(500, "default user missing; run bootstrap")
    return user


def current_language(user: AppUser = Depends(current_user)) -> str:
    """The language being studied: the user's active language when its pack is installed."""
    from app.packs import INSTALLED

    lang = user.active_language or "zh"
    if lang in INSTALLED:
        return lang
    return next(iter(INSTALLED), "zh")
