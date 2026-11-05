"""Client for the bhasha speech service (speech/ in this repo).

Hosts come from BHASHA_SPEECH_URLS, tried in order: put a GPU PC first and the
homelab's CPU container second, and audio keeps working when the PC is off.
Every clip is cached on disk, so a sentence is rendered once."""

import hashlib
import time
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import AppSetting, AudioClip

# Tests swap this for an httpx.MockTransport.
transport: httpx.BaseTransport | None = None

HEALTH_TTL = 30.0
_health: dict[str, tuple[float, dict | None]] = {}


def hosts() -> list[str]:
    return [u.strip().rstrip("/") for u in get_settings().speech_urls.split(",") if u.strip()]


def _headers() -> dict:
    token = get_settings().speech_token
    return {"Authorization": f"Bearer {token}"} if token else {}


def health(url: str, fresh: bool = False) -> dict | None:
    """The host's /health, or None when it doesn't answer. Cached briefly so an
    offline PC costs one short timeout per half minute, not one per request."""
    now = time.monotonic()
    cached = _health.get(url)
    if cached and not fresh and now - cached[0] < HEALTH_TTL:
        return cached[1]
    try:
        with httpx.Client(timeout=httpx.Timeout(3.0, connect=1.5), transport=transport) as c:
            info = c.get(f"{url}/health").raise_for_status().json()
    except (httpx.HTTPError, ValueError):
        info = None
    _health[url] = (now, info)
    return info


def active() -> tuple[str, dict] | None:
    for url in hosts():
        info = health(url)
        if info:
            return url, info
    return None


def setting(db: Session, key: str) -> dict:
    row = db.get(AppSetting, key)
    return dict(row.value) if row else {}


def put_setting(db: Session, key: str, value: dict) -> None:
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def voice_for(db: Session, info: dict | None) -> str | None:
    chosen = setting(db, "speech").get("voice")
    if info is None:
        return chosen
    return chosen if chosen in info.get("voices", []) else info.get("default_voice")


def clip_key(text: str, voice: str, speed: float) -> str:
    return hashlib.sha256(f"{voice}|{speed:.2f}|{text}".encode()).hexdigest()


class SpeechUnavailable(Exception):
    pass


def get_clip(db: Session, text: str, speed: float = 1.0, voice: str | None = None) -> AudioClip:
    """A cached clip, synthesizing it on the first healthy host if needed."""
    speed = round(speed, 2)
    host = active()
    voice = voice or voice_for(db, host[1] if host else None)
    if voice:
        hit = db.get(AudioClip, clip_key(text, voice, speed))
        if hit and (Path(get_settings().audio_cache_dir) / hit.path).is_file():
            return hit
    if host is None:
        raise SpeechUnavailable("No speech host is reachable.")
    url, info = host
    try:
        with httpx.Client(timeout=httpx.Timeout(120.0, connect=3.0), transport=transport) as c:
            r = c.post(f"{url}/tts", json={"text": text, "voice": voice, "speed": speed}, headers=_headers())
    except httpx.HTTPError as e:
        _health.pop(url, None)
        raise SpeechUnavailable(f"{url} stopped answering: {e}") from e
    if r.status_code == 401:
        raise SpeechUnavailable(f"{url} refused the token. Check BHASHA_SPEECH_TOKEN.")
    if r.status_code >= 400:
        raise SpeechUnavailable(f"{url} couldn't say that ({r.status_code}).")
    key = clip_key(text, voice, speed)
    rel = f"{key[:2]}/{key}.wav"
    path = Path(get_settings().audio_cache_dir) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    clip = db.get(AudioClip, key) or AudioClip(key=key)
    clip.text, clip.voice, clip.speed, clip.engine = text, voice, speed, info.get("engine", "?")
    clip.path, clip.size = rel, len(r.content)
    db.merge(clip)
    db.commit()
    return db.get(AudioClip, key)
