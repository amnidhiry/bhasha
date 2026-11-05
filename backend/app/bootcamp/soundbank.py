"""Audio for single syllables: recorded Tone Perfect files when imported, else a
common character with exactly that reading for the device's Mandarin voice.

A character is chosen only when that reading is its default (standalone)
reading, which is what a voice says for it on its own: 行 is used for xing2,
never for hang2."""

from collections import defaultdict

from pypinyin import Style, pinyin
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Unit


def _default_reading(ch: str) -> str:
    return pinyin(ch, style=Style.TONE3, neutral_tone_with_five=True)[0][0].replace("u:", "v").replace("ü", "v")




_bank: dict[str, str] | None = None


def build(db: Session) -> dict[str, str]:
    """syllable+tone (e.g. "ma3") -> most frequent unambiguous character."""
    global _bank
    if _bank is not None:
        return _bank
    best: dict[str, tuple[int, str]] = {}
    rows = db.execute(select(Unit.headword, Unit.reading, Unit.frequency_rank)
                      .where(Unit.language == "zh", Unit.type == "word"))
    for head, reading, rank in rows:
        syls = reading.split()
        if len(syls) != len(head):
            continue
        for ch, syl in zip(head, syls):
            if not syl[-1:].isdigit() or syl.endswith("5"):
                continue
            if _default_reading(ch) != syl:
                continue
            # Single-character words rank first: the voice reads them most naturally.
            score = (rank or 10**8) + (0 if len(head) == 1 else 50_000)
            if syl not in best or score < best[syl][0]:
                best[syl] = (score, ch)
    _bank = {syl: ch for syl, (_, ch) in best.items()}
    return _bank


def reset() -> None:
    global _bank
    _bank = None


def tones_available(bank: dict[str, str], syllable: str) -> list[int]:
    return [t for t in (1, 2, 3, 4) if f"{syllable}{t}" in bank]


def syllables(bank: dict[str, str]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = defaultdict(list)
    for key in bank:
        out[key[:-1]].append(int(key[-1]))
    return dict(out)
