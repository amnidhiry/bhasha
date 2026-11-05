"""Who is studying what: the installed language packs and the active language."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_language, current_user
from app.db import get_db
from app.models import AppUser
from app.packs import INSTALLED, get_pack

router = APIRouter(tags=["me"])


@router.get("/languages")
def languages():
    """Every installed pack with what the PWA needs to render it."""
    return [get_pack(code).meta() for code in INSTALLED]


@router.get("/me")
def me(user: AppUser = Depends(current_user), lang: str = Depends(current_language)):
    return {"name": user.name, "active_language": lang, "language": get_pack(lang).meta()}


class MeIn(BaseModel):
    active_language: str


@router.put("/me")
def update_me(body: MeIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    if body.active_language not in INSTALLED:
        raise HTTPException(400, f"no language pack installed for {body.active_language!r}")
    user.active_language = body.active_language
    db.commit()
    return {"name": user.name, "active_language": user.active_language,
            "language": get_pack(user.active_language).meta()}
