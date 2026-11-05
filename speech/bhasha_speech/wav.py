import io
import wave

import numpy as np


def to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Mono float samples in [-1, 1] -> 16-bit PCM WAV, playable everywhere (Safari included)."""
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()
