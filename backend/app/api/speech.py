from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import jobs as queue
from app.api.deps import current_user
from app.config import get_settings
from app.db import get_db
from app.models import AppUser
from app.speech import SpeechUnavailable, active, get_clip, health, hosts, put_setting, setting, voice_for

router = APIRouter(tags=["speech"])


@router.get("/tts")
def tts(text: str, speed: float = 0.85, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    """Audio for a word or sentence: cached, or synthesized on the first reachable
    speech host. 503 tells the PWA to use the device's own voice instead."""
    text = text.strip()
    if not text or len(text) > 400:
        raise HTTPException(400, "text must be 1-400 characters")
    if not hosts():
        raise HTTPException(503, "No speech host configured.")
    try:
        clip = get_clip(db, text, min(max(speed, 0.5), 1.5))
    except SpeechUnavailable as e:
        raise HTTPException(503, str(e))
    return FileResponse(Path(get_settings().audio_cache_dir) / clip.path, media_type="audio/wav",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})


@router.get("/speech")
def status(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    host = active()
    return {
        "hosts": [{"url": u, **({"online": True, **h} if (h := health(u, fresh=True)) else {"online": False})}
                  for u in hosts()],
        "active": host[0] if host else None,
        "voice": voice_for(db, host[1] if host else None),
        "voices": host[1].get("voices", []) if host else [],
        "tone_check": setting(db, "tone_check"),
    }


class VoiceIn(BaseModel):
    voice: str = Field(min_length=1, max_length=64)


@router.put("/speech/voice")
def set_voice(body: VoiceIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    host = active()
    if host and body.voice not in host[1].get("voices", []):
        raise HTTPException(400, f"{host[0]} has no voice {body.voice!r}")
    put_setting(db, "speech", {**setting(db, "speech"), "voice": body.voice})
    return status(db, user)


class CheckIn(BaseModel):
    voices: list[str] = Field(default_factory=list, max_length=12)


@router.post("/speech/tone-check", status_code=202)
def tone_check(body: CheckIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Score voices on Mandarin tones in the background (worker)."""
    if active() is None:
        raise HTTPException(409, "No speech host is reachable.")
    job = queue.enqueue(db, user.id, "tone_check", {"voices": body.voices})
    return {"job_id": job.id}
