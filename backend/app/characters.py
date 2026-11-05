"""Characters through their components: a component index built from Make Me a
Hanzi IDS decompositions, the learner's character status, and gentle notes on
characters whose parts mislead ("opaque" characters, docs/design.md).

Index: built on demand from `character_info` and cached in the process. Make Me
a Hanzi has ~9.5k entries, so a build takes a fraction of a second; computing it
at import time would need a new table (a migration) for no real gain. The cache
key includes the database, the row count and the latest import of each source,
so a re-import (or a test database) rebuilds it.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.learner import known_unit_ids
from app.models import Card, CharacterInfo, PackVersion, Unit, WordFrequency
from app.packs.zh.pinyin import citation_syllables, numeric_to_marks

# Ideographic description characters (⿰⿱…) and Make Me a Hanzi's "unknown part" marker.
_IDS = {chr(c) for c in range(0x2FF0, 0x3000)} | {"？"}

# Single strokes and bare frames. They are real parts, but "characters containing 一"
# says nothing useful, so they never head a group in the overview.
STROKES = set("一丨丿丶乙亅乚乛㇀⺀⺁冂冖亠丷八十二厶")

# Radical variants that belong to one family. The key is the family's name (the
# full form); the values are the forms Make Me a Hanzi uses inside characters.
# Simplified/traditional pairs of common radicals are merged too, since the
# dictionary decomposes traditional characters with traditional parts.
VARIANT_FAMILIES: dict[str, tuple[str, ...]] = {
    "水": ("氵", "氺"),
    "手": ("扌", "龵"),
    "言": ("讠", "訁"),
    "金": ("钅", "釒"),
    "人": ("亻",),
    "心": ("忄", "⺗", "㣺"),
    "糸": ("纟", "糹"),
    "食": ("饣", "飠"),
    "艸": ("艹", "⺾", "⺿"),
    "辵": ("辶", "⻌", "⻍", "⻎"),
    "刀": ("刂", "⺈"),
    "犬": ("犭",),
    "示": ("礻",),
    "衣": ("衤",),
    "火": ("灬",),
    "牛": ("牜",),
    "竹": ("⺮",),
    "网": ("罒", "⺲", "⺳", "罓"),
    "足": ("⻊", "𧾷"),
    "攴": ("攵",),
    "爪": ("爫",),
    "老": ("耂",),
    "肉": ("⺼",),
    "玉": ("⺩",),
    "羊": ("⺶", "⺷", "𦍌"),
    "爿": ("丬",),
    "贝": ("貝",),
    "见": ("見",),
    "马": ("馬",),
    "车": ("車",),
    "门": ("門",),
    "页": ("頁",),
    "鸟": ("鳥",),
    "鱼": ("魚",),
    "风": ("風",),
    "龙": ("龍",),
    "齿": ("齒",),
    "麦": ("麥",),
    "韦": ("韋",),
    "长": ("長",),
}
FAMILY_OF: dict[str, str] = {v: k for k, vs in VARIANT_FAMILIES.items() for v in vs}


def family(component: str) -> str:
    return FAMILY_OF.get(component, component)


def family_members(key: str) -> list[str]:
    """The forms of a family, the in-character forms first (氵 before 水)."""
    return [*VARIANT_FAMILIES.get(key, ()), key]


def parts(decomposition: str | None) -> list[str]:
    """Leaf components of an IDS string: '⿰钅艮' -> ['钅', '艮']. Unknown parts (？) are dropped."""
    return [c for c in (decomposition or "") if c not in _IDS]


# --- Pinyin comparison -------------------------------------------------------

_INITIALS = ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x", "r", "z", "c", "s")


def toneless(syllable: str) -> str:
    """'yín' -> 'yin', 'lǜ' -> 'lv', 'hao3' -> 'hao'."""
    s = syllable.strip().lower().replace("ü", "v").replace("u:", "v")
    for marked in "ǖǘǚǜ":
        s = s.replace(marked, "v")
    s = "".join(ch for ch in unicodedata.normalize("NFD", s) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z]", "", s)


def split_syllable(syllable: str) -> tuple[str, str]:
    """Toneless pinyin -> (initial, final) in the standard spelled-out form, so
    that y/w spellings compare like the sounds: 'yin' -> ('', 'in'),
    'wen' -> ('', 'uen'), 'qu' -> ('q', 'v'), 'zhi' -> ('zh', 'ɨ')."""
    s = toneless(syllable)
    if not s:
        return "", ""
    if s.startswith("y"):
        rest = s[1:]
        if rest.startswith("u"):
            return "", "v" + rest[1:]
        return "", rest if rest.startswith("i") else "i" + rest
    if s.startswith("w"):
        rest = s[1:]
        return "", rest if rest.startswith("u") else "u" + rest
    initial = next((i for i in _INITIALS if s.startswith(i) and len(s) > len(i)), "")
    final = s[len(initial):]
    if initial in ("j", "q", "x") and final.startswith("u"):
        final = "v" + final[1:]
    final = {"iu": "iou", "ui": "uei", "un": "uen", "vn": "vn"}.get(final, final)
    if final == "i" and initial in ("zh", "ch", "sh", "r", "z", "c", "s"):
        final = "ɨ"  # the buzzing vowel of zhi/zi, not the i of ji
    return initial, final


def rhyme(final: str) -> str:
    """The final without its medial glide: 'ian' -> 'an', 'uen' -> 'en', but 'in' stays 'in'."""
    if len(final) > 1 and final[0] in "iuv" and final[1] in "aeo":
        return final[1:]
    return final


def tone_number(syllable: str) -> int:
    for ch in unicodedata.normalize("NFD", syllable):
        if ch == "̄":
            return 1
        if ch == "́":
            return 2
        if ch == "̌":
            return 3
        if ch == "̀":
            return 4
    m = re.search(r"([1-5])$", syllable)
    return int(m.group(1)) if m else 5


def compare_sounds(char_reading: str, part_reading: str) -> str:
    """How well a sound part's reading hints at the character's:
    'same' (tone too), 'syllable' (only the tone differs), 'rhyme', 'initial', or 'none'."""
    ci, cf = split_syllable(char_reading)
    pi, pf = split_syllable(part_reading)
    if not cf or not pf:
        return "none"
    if (ci, cf) == (pi, pf):
        return "same" if tone_number(char_reading) == tone_number(part_reading) else "syllable"
    if rhyme(cf) == rhyme(pf):
        return "rhyme"
    if ci and ci == pi:
        return "initial"
    return "none"


_MATCH_ORDER = ["same", "syllable", "rhyme", "initial", "none"]


# --- The index ---------------------------------------------------------------


@dataclass
class CharEntry:
    character: str
    definition: str | None
    pinyin: list[str]
    decomposition: str | None
    radical: str | None
    etymology: dict | None
    parts: list[str]
    # family -> (depth, via): depth 1 is a direct part; via is the direct part it sits in.
    contains: dict[str, tuple[int, str]] = field(default_factory=dict)
    notes: list[dict] = field(default_factory=list)
    transparency: str = "unknown"  # clear | partial | opaque | unknown


@dataclass
class Index:
    chars: dict[str, CharEntry]
    by_family: dict[str, list[str]]  # family -> characters containing it at any depth
    freq: dict[str, tuple[int, float]]  # character -> (rank, per million)


_lock = threading.Lock()
_cache: dict[tuple, Index] = {}


def _cache_key(db: Session) -> tuple:
    versions = tuple(db.execute(
        select(PackVersion.component, func.max(PackVersion.id))
        .where(PackVersion.component.in_(("makemeahanzi", "subtlex-ch-wf")))
        .group_by(PackVersion.component).order_by(PackVersion.component)
    ).all())
    count = db.scalar(select(func.count()).select_from(CharacterInfo)) or 0
    freq_count = db.scalar(select(func.count()).select_from(WordFrequency)) or 0
    return (str(db.get_bind().url), count, freq_count, versions)


def get_index(db: Session) -> Index:
    key = _cache_key(db)
    with _lock:
        idx = _cache.get(key)
        if idx is None:
            _cache.clear()
            idx = _cache[key] = build_index(db)
        return idx


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _char_frequency(db: Session) -> dict[str, tuple[int, float]]:
    """Character frequency from SUBTLEX-CH word frequencies: a character's count is
    the sum over every word it appears in (so 银 gets credit for 银行)."""
    per_million: dict[str, float] = defaultdict(float)
    for word, pm in db.execute(select(WordFrequency.word, WordFrequency.per_million)):
        for ch in set(word):
            if "㐀" <= ch <= "鿿" or "\U00020000" <= ch <= "\U0002ffff":
                per_million[ch] += pm
    ranked = sorted(per_million.items(), key=lambda kv: -kv[1])
    return {ch: (i + 1, pm) for i, (ch, pm) in enumerate(ranked)}


def build_index(db: Session) -> Index:
    chars: dict[str, CharEntry] = {}
    for row in db.scalars(select(CharacterInfo)):
        chars[row.character] = CharEntry(
            character=row.character, definition=row.definition, pinyin=list(row.pinyin or []),
            decomposition=row.decomposition, radical=row.radical, etymology=row.etymology,
            parts=parts(row.decomposition),
        )

    memo: dict[str, dict[str, tuple[int, str]]] = {}

    def contains(ch: str, stack: frozenset[str]) -> dict[str, tuple[int, str]]:
        if ch in memo:
            return memo[ch]
        out: dict[str, tuple[int, str]] = {}
        entry = chars.get(ch)
        for p in entry.parts if entry else []:
            if p == ch:
                continue
            f = family(p)
            if f not in out or out[f][0] > 1:
                out[f] = (1, p)
            if p in stack:
                continue  # guard against cycles in hand-made data
            for sub_f, (depth, _) in contains(p, stack | {ch}).items():
                if sub_f == family(ch):
                    continue
                if sub_f not in out or out[sub_f][0] > depth + 1:
                    out[sub_f] = (depth + 1, p)
        memo[ch] = out
        return out

    by_family: dict[str, list[str]] = defaultdict(list)
    for ch, entry in chars.items():
        entry.contains = contains(ch, frozenset())
        for f in entry.contains:
            by_family[f].append(ch)

    idx = Index(chars=chars, by_family=dict(by_family), freq=_char_frequency(db))
    for entry in chars.values():
        entry.notes, entry.transparency = explain(entry, idx)
    return idx


# --- Opaque-character notes --------------------------------------------------


def readings_of(idx: Index, ch: str) -> list[str]:
    """Tone-marked readings: Make Me a Hanzi's, else pypinyin's (some components have none)."""
    entry = idx.chars.get(ch)
    if entry and entry.pinyin:
        return entry.pinyin
    if len(ch) == 1 and "㐀" <= ch <= "鿿":
        syl = citation_syllables(ch)[0]
        if re.match(r"^[a-z]+[1-5]$", syl):
            return [numeric_to_marks(syl)]
    return []


def short_gloss(definition: str | None) -> str | None:
    """'and, also, again, in addition' -> 'and'; 'moon; month' -> 'moon'."""
    if not definition:
        return None
    return re.split(r"[;,]", definition)[0].strip() or None


def _mentioned(part: str, hint: str) -> bool:
    return any(m in hint for m in family_members(family(part))) or part in hint


def explain(entry: CharEntry, idx: Index) -> tuple[list[dict], str]:
    """Notes on how far a character's parts help, from Make Me a Hanzi data alone.

    Conservative by design; only two things count as misleading:
    1. a sound part whose reading shares neither the initial nor the rhyme with any
       of the character's readings (银 yín, sound part 艮 gěn);
    2. a part of a meaning compound (ideographic) that its etymology never uses,
       e.g. 又 in 汉, a shape left over from simplification.
    Missing etymologies are reported as unknown, never as opaque."""
    ety = entry.etymology or {}
    kind = ety.get("type")
    hint = (ety.get("hint") or "").replace("\xa0", " ")
    notes: list[dict] = []
    real_parts = [p for p in entry.parts if p != entry.character]
    status = "unknown"

    if kind == "pictophonetic":
        semantic, phonetic = ety.get("semantic"), ety.get("phonetic")
        if semantic:
            notes.append({"kind": "meaning", "component": semantic,
                          "text": f"The meaning part {semantic} points to {hint or short_gloss(_def(idx, semantic)) or 'the meaning'}."})
        status = "partial"
        if phonetic:
            mine = entry.pinyin or readings_of(idx, entry.character)
            theirs = readings_of(idx, phonetic)
            best = None
            for a in mine:
                for b in theirs:
                    m = compare_sounds(a, b)
                    if best is None or _MATCH_ORDER.index(m) < _MATCH_ORDER.index(best[0]):
                        best = (m, a, b)
            if best:
                m, a, b = best
                head = f"The sound part {phonetic} ({b})"
                if m == "same":
                    text, status = f"{head} gives the reading {a}.", "clear"
                elif m == "syllable":
                    text, status = f"{head} gives the sound; only the tone differs ({a}).", "clear"
                elif m == "rhyme":
                    text, status = f"{head} rhymes with {a}, so it's a partial hint.", "partial"
                elif m == "initial":
                    text, status = f"{head} starts like {a} but ends differently, so it's a weak hint.", "partial"
                else:
                    text, status = f"{head} doesn't hint at {a} here.", "opaque"
                notes.append({"kind": f"sound_{'helps' if status == 'clear' else 'partial' if status == 'partial' else 'misleading'}",
                              "component": phonetic, "text": text, "match": m})
        else:
            rest = [p for p in real_parts if family(p) != family(semantic or "")]
            if rest:
                notes.append({"kind": "no_sound_part", "component": None,
                              "text": f"Only the meaning part is identified; {' + '.join(rest)} isn't recorded as a sound hint."})
    elif kind == "ideographic":
        unexplained = [p for p in real_parts if p not in STROKES and not _mentioned(p, hint)]
        if hint:
            notes.append({"kind": "story", "component": None, "text": hint})
        # Only judge when the story names at least one part, so it is about the parts at all.
        if hint and unexplained and len(unexplained) < len(real_parts):
            for p in unexplained:
                gloss = short_gloss(_def(idx, p))
                usual = f" (usually “{gloss}”)" if gloss else ""
                why = "simplification put it there" if "simplif" in hint.lower() else "its story doesn't use it"
                notes.append({"kind": "part_misleading", "component": p,
                              "text": f"The part {p}{usual} doesn't carry its own meaning here; {why}."})
            status = "opaque"
        elif hint:
            status = "clear"
    elif kind == "pictographic":
        if hint:
            notes.append({"kind": "picture", "component": None,
                          "text": f"Originally a picture: {hint[0].lower() + hint[1:]}."})
        if len(real_parts) > 1:
            notes.append({"kind": "picture_parts", "component": None,
                          "text": f"The parts {' + '.join(real_parts)} are pieces of that picture rather than separate clues."})
        status = "clear"
    elif len(real_parts) > 1:
        notes.append({"kind": "no_etymology", "component": None,
                      "text": "Its origin isn't recorded here, so treat " + " + ".join(real_parts) + " as shapes to remember rather than clues."})
    return notes, status


def _def(idx: Index, ch: str) -> str | None:
    e = idx.chars.get(ch)
    return e.definition if e else None


# --- The learner's characters ------------------------------------------------


def character_status(db: Session, user_id: int, language: str = "zh") -> dict[str, str]:
    """'known' when the character appears in a known word (as Progress counts it),
    'learning' when it appears in a word with cards or has its own (handwriting) card."""
    known_ids = known_unit_ids(db, user_id, language)
    carded = set(db.scalars(select(Card.unit_id).where(Card.user_id == user_id).distinct()))
    ids = known_ids | carded
    out: dict[str, str] = {}
    if not ids:
        return out
    ids_list = list(ids)
    units: list[tuple[int, str]] = []
    for i in range(0, len(ids_list), 900):
        units += db.execute(select(Unit.id, Unit.headword).where(
            Unit.id.in_(ids_list[i:i + 900]), Unit.language == language,
            Unit.type.in_(("word", "character")))).all()
    for uid, head in units:
        if uid in known_ids:
            for ch in head:
                out[ch] = "known"
    for uid, head in units:
        if uid not in known_ids:
            for ch in head:
                out.setdefault(ch, "learning")
    return {ch: s for ch, s in out.items() if _is_han(ch)}


def _is_han(ch: str) -> bool:
    return "㐀" <= ch <= "鿿" or "\U00020000" <= ch <= "\U0002ffff" or "豈" <= ch <= "﫿"


STATUS_ORDER = {"known": 0, "learning": 1}


def char_summary(idx: Index, ch: str, status: dict[str, str]) -> dict:
    e = idx.chars.get(ch)
    rank = idx.freq.get(ch)
    return {
        "character": ch,
        "pinyin": e.pinyin if e else [],
        "definition": e.definition if e else None,
        "status": status.get(ch, "new"),
        "frequency_rank": rank[0] if rank else None,
        "transparency": e.transparency if e else "unknown",
    }


def rank_key(idx: Index, status: dict[str, str]):
    def key(ch: str):
        rank = idx.freq.get(ch)
        return (STATUS_ORDER.get(status.get(ch, ""), 2), rank[0] if rank else 10**9, ch)
    return key


def family_info(idx: Index, key: str) -> dict:
    """Display data for a component family."""
    members = [m for m in family_members(key) if m == key or m in idx.chars or m in idx.by_family]
    e = idx.chars.get(key) or next((idx.chars[m] for m in members if m in idx.chars), None)
    return {"key": key, "members": members, "definition": e.definition if e else None,
            "pinyin": readings_of(idx, key)}


def productive_groups(idx: Index, mine: list[str], limit: int = 12, max_depth: int = 1) -> list[dict]:
    """Components that are a direct part of the most of the learner's characters,
    at least two each. Direct parts only: one level down mostly finds shapes inside
    shapes (口 inside 日 in 时, 人 inside 大 in 天), which are noise as groups. The
    explorer still follows parts of parts."""
    counts: dict[str, list[str]] = defaultdict(list)
    for ch in mine:
        e = idx.chars.get(ch)
        if not e:
            continue
        for f, (depth, _) in e.contains.items():
            if depth <= max_depth and f not in STROKES and not any(m in STROKES for m in family_members(f)):
                counts[f].append(ch)
    ranked = sorted((f for f in counts if len(counts[f]) >= 2), key=lambda f: (-len(counts[f]), f))
    return [{**family_info(idx, f), "count": len(counts[f]), "characters": counts[f]} for f in ranked[:limit]]
