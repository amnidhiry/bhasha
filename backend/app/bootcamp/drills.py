"""Drill items for the sound bootcamp. Every item carries its own answer: these
are self-checked listening drills, not tests.

Weak spots come up more: tones and contrasts are sampled with weight
(1 - recent accuracy) + a floor, so nothing disappears entirely.
"""

import random
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.bootcamp import content, soundbank
from app.models import AudioSyllable, DrillAttempt, Unit
from app.packs.zh.pinyin import apply_sandhi, citation_syllables, numeric_to_marks, tone_of

FLOOR = 0.15


def _plain(syllable: str) -> str:
    """Pinyin without tone marks, as shown before the answer: 'lv' -> 'lü'."""
    return syllable.replace("v", "ü")


def recent(db: Session, user_id: int, drill_prefix: str, window: int = content.MASTERY_WINDOW) -> dict[str, list[bool]]:
    """Recent results per drill whose id starts with drill_prefix, newest first."""
    rows = db.execute(
        select(DrillAttempt.drill, DrillAttempt.item, DrillAttempt.correct)
        .where(DrillAttempt.user_id == user_id, DrillAttempt.drill.startswith(drill_prefix))
        .order_by(DrillAttempt.at.desc(), DrillAttempt.id.desc()).limit(2000)
    )
    out: dict[str, list[bool]] = defaultdict(list)
    for drill, item, correct in rows:
        if len(out[drill]) < window:
            out[drill].append(correct)
        if drill == "tone":  # per-tone results for weighting
            key = f"tone:{item[-1]}"
            if len(out[key]) < window:
                out[key].append(correct)
    return out


def accuracy(results: list[bool]) -> float | None:
    return sum(results) / len(results) if results else None


def _weight(results: list[bool]) -> float:
    acc = accuracy(results)
    return (1.0 - acc if acc is not None else 0.6) + FLOOR


def _audio(db: Session, key: str, char: str | None = None, text: str | None = None) -> dict:
    speakers = [s for (s,) in db.execute(select(AudioSyllable.speaker).where(AudioSyllable.key == key))] if key else []
    return {"key": key, "char": char, "text": text or char, "speakers": sorted(speakers)}


def tone_items(db: Session, user_id: int, n: int, rng: random.Random) -> list[dict]:
    bank = soundbank.build(db)
    by_tone: dict[int, list[str]] = defaultdict(list)
    for key in bank:
        syl, t = key[:-1], int(key[-1])
        if len(soundbank.tones_available(bank, syl)) >= 3:  # syllables with real tone choices
            by_tone[t].append(key)
    tones = [t for t in (1, 2, 3, 4) if by_tone[t]]
    if not tones:
        return []  # no HSK data imported yet
    stats = recent(db, user_id, "tone")
    weights = [_weight(stats.get(f"tone:{t}", [])) for t in tones]
    items = []
    for _ in range(n):
        t = rng.choices(tones, weights)[0]
        key = rng.choice(by_tone[t])
        syl = key[:-1]
        items.append({
            "drill": "tone", "item": key, "prompt": _plain(syl),
            "audio": _audio(db, key, bank[key]),
            "options": [{"value": str(x), "label": numeric_to_marks(f"{syl}{x}")} for x in (1, 2, 3, 4)],
            "answer": str(t),
            "reveal": f"{bank[key]} {numeric_to_marks(key)}",
        })
    return items


def _two_syllable_words(db: Session, limit: int = 600) -> list[tuple[str, list[str]]]:
    rows = db.execute(
        select(Unit.headword, Unit.reading, Unit.frequency_rank)
        .where(Unit.language == "zh", Unit.type == "word").order_by(Unit.frequency_rank)
    )
    out, seen = [], set()
    for head, reading, _ in rows:
        syls = reading.split()
        if len(head) != 2 or len(syls) != 2 or head in seen:
            continue
        if any(tone_of(s) is None for s in syls):
            continue
        seen.add(head)
        out.append((head, syls))
        if len(out) >= limit:
            break
    return out


def pair_items(db: Session, user_id: int, n: int, rng: random.Random) -> list[dict]:
    """Hear a whole word; answer the tones as spoken (surface tones, after sandhi)."""
    words = _two_syllable_words(db)
    items = []
    for head, syls in rng.sample(words, min(n, len(words))):
        surface = apply_sandhi([(head, syls)])[0]
        answer = "".join(str(tone_of(s)) for s in surface)
        items.append({
            "drill": "pair", "item": head, "prompt": " ".join(_plain(s[:-1]) for s in syls),
            "audio": _audio(db, "", text=head),
            "options": None, "answer": answer,
            "reveal": f"{head} {' '.join(numeric_to_marks(s) for s in surface)}",
        })
    return items


SANDHI_WORDS = ["你好", "可以", "水果", "很好", "老鼠", "洗澡", "小姐", "手表", "雨伞", "所以", "了解", "厂长",
                "不是", "不对", "不去", "不要", "不看", "不吃", "不来", "不好",
                "一个", "一样", "一定", "一起", "一天", "一年", "一点", "一下"]


def sandhi_items(db: Session, user_id: int, n: int, rng: random.Random) -> list[dict]:
    """See the word with dictionary tones; answer how it's actually said."""
    items = []
    for head in rng.sample(SANDHI_WORDS, min(n, len(SANDHI_WORDS))):
        cite = citation_syllables(head)
        surface = apply_sandhi([(head, cite)])[0]
        items.append({
            "drill": "sandhi", "item": head,
            "prompt": f"{head}  ·  written {' '.join(numeric_to_marks(s) for s in cite)}",
            "audio": _audio(db, "", text=head), "options": None,
            "answer": "".join(str(tone_of(s)) for s in surface),
            "reveal": f"said {' '.join(numeric_to_marks(s) for s in surface)}",
        })
    return items


def contrast_items(db: Session, user_id: int, contrast_id: str, n: int, rng: random.Random) -> list[dict]:
    spec = next((c for c in content.CONTRASTS if c["id"] == contrast_id), None)
    if spec is None:
        raise KeyError(contrast_id)
    bank = soundbank.build(db)
    playable = []
    for a, b in spec["pairs"]:
        shared = sorted(set(soundbank.tones_available(bank, a)) & set(soundbank.tones_available(bank, b)))
        if shared:
            playable.append((a, b, shared))
    if not playable:
        return []
    items = []
    for _ in range(n):
        a, b, shared = rng.choice(playable)
        t = rng.choice(shared)
        pick = rng.choice((a, b))
        options = [a, b]
        rng.shuffle(options)
        key = f"{pick}{t}"
        items.append({
            "drill": f"contrast:{contrast_id}", "item": f"{a}{t}|{b}{t}", "prompt": "Which did you hear?",
            "audio": _audio(db, key, bank[key]),
            "options": [{"value": o, "label": numeric_to_marks(f"{o}{t}"), "audio": _audio(db, f"{o}{t}", bank[f"{o}{t}"])}
                        for o in options],
            "answer": pick,
            "reveal": f"{bank[key]} {numeric_to_marks(key)}",
        })
    return items


def make(db: Session, user_id: int, drill: str, n: int = 10, seed: int | None = None) -> list[dict]:
    rng = random.Random(seed)
    if drill == "tone":
        return tone_items(db, user_id, n, rng)
    if drill == "pair":
        return pair_items(db, user_id, n, rng)
    if drill == "sandhi":
        return sandhi_items(db, user_id, n, rng)
    if drill.startswith("contrast:"):
        return contrast_items(db, user_id, drill.split(":", 1)[1], n, rng)
    raise KeyError(drill)


def overview(db: Session, user_id: int) -> dict:
    stats = recent(db, user_id, "")
    drills = []
    for d in content.DRILLS:
        res = stats.get(d["id"], [])
        acc = accuracy(res)
        drills.append({**d, "attempts": len(res), "accuracy": acc,
                       "mastered": len(res) >= content.MASTERY_WINDOW and (acc or 0) >= content.MASTERY_ACCURACY})
    tones = {str(t): accuracy(stats.get(f"tone:{t}", [])) for t in (1, 2, 3, 4)}
    recorded = db.scalar(select(AudioSyllable.id).limit(1)) is not None
    return {"drills": drills, "tone_accuracy": tones, "recorded_audio": recorded,
            "mastery": {"window": content.MASTERY_WINDOW, "accuracy": content.MASTERY_ACCURACY}}
