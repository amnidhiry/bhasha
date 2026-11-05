"""bhasha speech service: POST /tts {text, voice, speed} -> audio/wav.

Environment:
  SPEECH_ENGINE  kokoro (default) | synth
  SPEECH_DEVICE  auto (default) | cpu | cuda
  SPEECH_TOKEN   shared secret; bhasha sends it as a Bearer token. Set it on any
                 host reachable from the LAN.
"""

import os
import threading
import time

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from bhasha_speech.engines import load
from bhasha_speech.wav import to_wav

MAX_CHARS = 400

engine = load(os.environ.get("SPEECH_ENGINE", "kokoro"), os.environ.get("SPEECH_DEVICE", "auto"))
_lock = threading.Lock()  # one synthesis at a time: models aren't thread-safe and the CPU is shared
app = FastAPI(title="bhasha-speech")


def auth(authorization: str | None = Header(default=None)) -> None:
    token = os.environ.get("SPEECH_TOKEN", "")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "bad or missing token")


@app.get("/health")
def health():
    return {"ok": True, "engine": engine.name, "device": engine.device, "voices": engine.voices,
            "default_voice": engine.default_voice, "sample_rate": engine.sample_rate}


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_CHARS)
    voice: str | None = None
    speed: float = Field(default=1.0, ge=0.5, le=1.5)


@app.post("/tts", dependencies=[Depends(auth)])
def tts(body: TtsIn):
    voice = body.voice or engine.default_voice
    if voice not in engine.voices:
        raise HTTPException(400, f"unknown voice {voice!r}; have {engine.voices}")
    t0 = time.monotonic()
    with _lock:
        audio = engine.synthesize(body.text, voice, body.speed)
    if audio.size == 0:
        raise HTTPException(422, "nothing to say")
    return Response(to_wav(audio, engine.sample_rate), media_type="audio/wav",
                    headers={"X-Engine": engine.name, "X-Voice": voice, "X-Device": engine.device,
                             "X-Seconds": f"{time.monotonic() - t0:.3f}"})
