"""Kokoro-82M (Apache-2.0) with its Mandarin pipeline (lang_code "z", misaki[zh]
G2P). Small enough to run faster than real time on a CPU; much faster on CUDA.
Weights and voices download from Hugging Face on first use into HF_HOME.

KOKORO_REPO picks the model: hexgrad/Kokoro-82M (v1.0, default, 8 Mandarin
voices) or hexgrad/Kokoro-82M-v1.1-zh (trained for Chinese, many voices).
Mandarin voices are listed from the repo itself, so either works without code
changes. Upstream marks v1.0's Chinese as partial; bhasha's tone check
(Progress -> Voice) scores each voice before you rely on it."""

import os

import numpy as np

V1_MANDARIN = ["zf_xiaobei", "zf_xiaoni", "zf_xiaoxiao", "zf_xiaoyi", "zm_yunjian", "zm_yunxi", "zm_yunxia", "zm_yunyang"]


def _repo_voices(repo: str) -> list[str]:
    try:
        from huggingface_hub import list_repo_files

        names = [f.split("/")[-1][:-3] for f in list_repo_files(repo) if f.startswith("voices/") and f.endswith(".pt")]
        zh = sorted(n for n in names if n[:2] in ("zf", "zm"))
        return zh or V1_MANDARIN
    except Exception:  # offline: fall back to v1.0's known voices
        return V1_MANDARIN


class KokoroEngine:
    name = "kokoro"
    sample_rate = 24000

    def __init__(self, device: str = "auto"):
        import torch
        from kokoro import KPipeline

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.repo = os.environ.get("KOKORO_REPO", "hexgrad/Kokoro-82M")
        self.voices = _repo_voices(self.repo)
        self.default_voice = "zf_xiaoxiao" if "zf_xiaoxiao" in self.voices else self.voices[0]
        self.pipeline = KPipeline(lang_code="z", repo_id=self.repo, device=device)

    def synthesize(self, text: str, voice: str, speed: float) -> np.ndarray:
        chunks = []
        for result in self.pipeline(text, voice=voice, speed=speed):
            audio = result[2] if isinstance(result, tuple) else getattr(result, "audio", None)
            if audio is None:
                continue
            if hasattr(audio, "detach"):  # torch tensor, possibly on the GPU
                audio = audio.detach().cpu().numpy()
            chunks.append(np.asarray(audio, dtype=np.float32))
        return np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
