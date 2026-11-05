from typing import Protocol

import numpy as np


class Engine(Protocol):
    name: str
    device: str
    sample_rate: int
    voices: list[str]
    default_voice: str

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray: ...


def load(name: str, device: str) -> Engine:
    if name == "kokoro":
        from bhasha_speech.engines.kokoro_engine import KokoroEngine

        return KokoroEngine(device)
    if name == "synth":
        from bhasha_speech.engines.synth import ToneSynth

        return ToneSynth()
    raise ValueError(f"unknown SPEECH_ENGINE {name!r} (kokoro, synth)")
