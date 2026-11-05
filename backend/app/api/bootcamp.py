import random
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.bootcamp import content, drills, soundbank
from app.config import get_settings
from app.db import get_db
from app.models import AppUser, AudioSyllable, DrillAttempt
from app.packs.zh.pinyin import numeric_to_marks

router = APIRouter(tags=["bootcamp"])


@router.get("/bootcamp")
def bootcamp(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Lessons, drills and your accuracy on each."""
    bank = soundbank.build(db)

    def sample(syl: str) -> list[dict]:
        return [{"key": f"{syl}{t}", "label": numeric_to_marks(f"{syl}{t}"), "char": bank[f"{syl}{t}"]}
                for t in (1, 2, 3, 4) if f"{syl}{t}" in bank]

    return {
        "tones": content.TONES,
        "tone_examples": sample("ma"),
        "initial_groups": [
            {**g, "audio": [s for ex in g["examples"] for s in sample(ex)[:1]]} for g in content.INITIAL_GROUPS
        ],
        "final_notes": content.FINAL_NOTES,
        **drills.overview(db, user.id),
    }


@router.get("/bootcamp/drill")
def drill(drill: str, n: int = 10, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    try:
        return drills.make(db, user.id, drill, max(1, min(n, 30)))
    except KeyError:
        raise HTTPException(404, f"no drill {drill!r}")


class AttemptIn(BaseModel):
    drill: str = Field(max_length=48)
    item: str = Field(max_length=64)
    answer: str = Field(max_length=32)
    correct: bool


@router.post("/bootcamp/attempts")
def attempts(body: list[AttemptIn], db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    db.add_all(DrillAttempt(user_id=user.id, **a.model_dump()) for a in body)
    db.commit()
    return drills.overview(db, user.id)


@router.get("/audio/{key}")
def audio(key: str, speaker: str | None = None, db: Session = Depends(get_db)):
    """A recorded syllable (Tone Perfect), e.g. /api/audio/ma3?speaker=FV1."""
    q = select(AudioSyllable).where(AudioSyllable.key == key)
    if speaker:
        q = q.where(AudioSyllable.speaker == speaker)
    rows = list(db.scalars(q))
    if not rows:
        raise HTTPException(404, "no recording for this syllable")
    row = random.choice(rows)
    root = Path(get_settings().audio_dir).resolve()
    path = (root / row.path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "recording file missing")
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=31536000"})
