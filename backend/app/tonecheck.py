"""Does a TTS voice get Mandarin tones right? Synthesize common single characters
for each tone and classify their pitch contours with the same YIN tracker and
rules as the PWA's "Say it" (web/src/pitch.ts), ported to NumPy.

A wrong-tone voice teaches wrong tones, so this score, not general naturalness,
decides which voice bhasha uses. NumPy is in the worker image; this runs there."""

import io
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session

from app.bootcamp import soundbank
from app.config import get_settings

PER_TONE = 6


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data)) as w:
        raw = w.readframes(w.getnframes())
        sr = w.getframerate()
        width, ch = w.getsampwidth(), w.getnchannels()
    if width != 2:
        raise ValueError("expected 16-bit PCM")
    x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768
    return (x.reshape(-1, ch).mean(axis=1) if ch > 1 else x), sr


def yin(frame: np.ndarray, sr: int, min_f=70.0, max_f=500.0, threshold=0.15) -> float | None:
    max_lag = min(int(sr / min_f), len(frame) // 2)
    min_lag = max(2, int(sr / max_f))
    if float(np.mean(frame ** 2)) < 1e-6:
        return None
    n = len(frame) - max_lag
    base = frame[:n]
    d = np.array([0.0] + [float(np.sum((base - frame[lag:lag + n]) ** 2)) for lag in range(1, max_lag + 1)])
    cum = np.cumsum(d[1:])
    cmnd = np.ones_like(d)
    with np.errstate(divide="ignore", invalid="ignore"):
        cmnd[1:] = np.where(cum > 0, d[1:] * np.arange(1, max_lag + 1) / cum, 1.0)
    below = np.nonzero(cmnd[min_lag:] < threshold)[0]
    if below.size == 0:
        return None
    tau = int(below[0]) + min_lag
    while tau + 1 <= max_lag and cmnd[tau + 1] < cmnd[tau]:
        tau += 1
    a, b, c = cmnd[tau - 1], cmnd[tau], cmnd[min(tau + 1, max_lag)]
    denom = a + c - 2 * b
    shift = (a - c) / (2 * denom) if denom else 0.0
    return sr / (tau + shift)


def track(x: np.ndarray, sr: int, hop=0.01, win=0.04) -> list[float | None]:
    w, h = int(win * sr), int(hop * sr)
    return [yin(x[i:i + w], sr) for i in range(0, len(x) - w + 1, h)]


def contour(f0: list[float | None]) -> list[float]:
    runs, cur = [], []
    for f in [*f0, None]:
        if f:
            cur.append(f)
        else:
            if cur:
                runs.append(cur)
            cur = []
    best = max(runs, key=len, default=[])
    if len(best) < 5:
        return []
    ref = float(np.median(best))
    st = [12 * np.log2(f / ref) for f in best]
    st = [v - 12 if v > 9 else v + 12 if v < -9 else v for v in st]
    return [float(np.median(st[max(0, i - 2):i + 3])) for i in range(len(st))]


def classify(c: list[float]) -> int | None:
    """Same rules as pitch.ts classify()."""
    if len(c) < 5:
        return None
    trim = int(len(c) * 0.1)
    x = c[trim:len(c) - trim] if trim else c
    k = max(1, int(len(x) * 0.2))
    start, end = float(np.mean(x[:k])), float(np.mean(x[-k:]))
    lo, hi = min(x), max(x)
    pos = x.index(lo) / (len(x) - 1)
    if end - start <= -3:
        return 4
    # Third tone: the low point comes after the first quarter, with some dip before
    # it and a rise after. (A second tone's dip, if any, is small and early.)
    if start - lo >= 0.7 and end - lo >= 1.5 and 0.25 < pos < 0.85:
        return 3
    if end - start >= 2.5:
        return 2
    if hi - lo < 2:
        return 1
    return None


def items(db: Session) -> list[tuple[str, str, int]]:
    """(key, character, tone): the most common unambiguous characters per tone."""
    bank = soundbank.build(db)
    by_tone: dict[int, list[tuple[str, str]]] = {1: [], 2: [], 3: [], 4: []}
    for key, ch in sorted(bank.items()):
        t = int(key[-1])
        if t in by_tone and len(soundbank.tones_available(bank, key[:-1])) >= 3:
            by_tone[t].append((key, ch))
    out = []
    for t, pairs in by_tone.items():
        step = max(1, len(pairs) // PER_TONE)
        out += [(k, ch, t) for k, ch in pairs[::step][:PER_TONE]]
    return out


def check_voice(db: Session, voice: str, speed: float = 0.85) -> dict:
    from app.speech import get_clip

    results, per_tone = [], {str(t): [0, 0] for t in (1, 2, 3, 4)}
    root = Path(get_settings().audio_cache_dir)
    for key, ch, tone in items(db):
        clip = get_clip(db, ch, speed, voice=voice)
        x, sr = read_wav((root / clip.path).read_bytes())
        got = classify(contour(track(x, sr)))
        per_tone[str(tone)][1] += 1
        per_tone[str(tone)][0] += int(got == tone)
        results.append({"key": key, "char": ch, "tone": tone, "heard": got})
    right = sum(v[0] for v in per_tone.values())
    total = sum(v[1] for v in per_tone.values())
    return {"voice": voice, "accuracy": right / total if total else None, "n": total,
            "per_tone": {t: (v[0] / v[1] if v[1] else None) for t, v in per_tone.items()},
            "misses": [r for r in results if r["heard"] != r["tone"]][:12],
            "at": datetime.now(timezone.utc).isoformat()}
