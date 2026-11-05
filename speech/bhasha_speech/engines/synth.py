"""A model-free tone synthesizer: each syllable becomes a voiced tone with the
textbook Chao contour (55, 35, 214, 51, neutral short). It sounds robotic and is
not for learning words; it exists so the whole speech path, and bhasha's tone
check, can be tested on any machine without downloading a model."""

import numpy as np
from pypinyin import Style, lazy_pinyin

CHAO = {1: (5, 5), 2: (3, 5), 3: (2, 1, 4), 4: (5, 1), 5: (3, 3)}
BASE_HZ = 160.0  # Chao level 1
STEP = 2 ** (2.2 / 12)  # ~2.2 semitones per Chao level


class ToneSynth:
    name = "synth"
    device = "cpu"
    sample_rate = 24000
    voices = ["tones"]
    default_voice = "tones"

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray:
        sr = self.sample_rate
        out = []
        for syl in lazy_pinyin(text, style=Style.TONE3, neutral_tone_with_five=True, errors="ignore"):
            tone = int(syl[-1]) if syl[-1:].isdigit() else 5
            dur = (0.18 if tone == 5 else 0.42) / speed
            n = int(sr * dur)
            t = np.linspace(0, 1, n)
            levels = CHAO[tone]
            pts = np.interp(t, np.linspace(0, 1, len(levels)), levels)
            f0 = BASE_HZ * STEP ** (pts - 1)
            phase = np.cumsum(2 * np.pi * f0 / sr)
            wave = 0.5 * np.sin(phase) + 0.25 * np.sin(2 * phase) + 0.12 * np.sin(3 * phase)
            env = np.minimum(1, np.minimum(t * 25, (1 - t) * 25))
            out += [wave * env * 0.6, np.zeros(int(sr * 0.08))]
        return np.concatenate(out).astype(np.float32) if out else np.zeros(0, dtype=np.float32)
