"""Pinyin with separate citation and surface (spoken) tones.

pypinyin supplies context-aware citation readings per word (its phrase dictionary
resolves most polyphones such as 银行 vs 行走). pypinyin's phrase data already
bakes 一/不 sandhi into some entries, so we normalize those back to citation
tones first and then apply our own sandhi rules on top:

1. 不 bù becomes bú before a fourth tone.
2. 一 yī becomes yí before a fourth tone and yì before tones 1-3, but stays yī
   when used as a number (after 第, at the end of a phrase, or inside a numeral).
3. Third-tone sandhi: in a run of third tones inside a word, all but the last
   become second tone (展览馆 zhán lán guǎn). Across word boundaries, working
   right to left, a third tone before a third tone becomes second (我很好 wǒ hén hǎo).

These are heuristics for a reading aid, not a prosody model; see docs/design.md.
"""

import re

from pypinyin import Style, lazy_pinyin

_TONE_MARKS = {
    "a": "āáǎà",
    "e": "ēéěè",
    "i": "īíǐì",
    "o": "ōóǒò",
    "u": "ūúǔù",
    "v": "ǖǘǚǜ",
}
_SYLLABLE_RE = re.compile(r"^([a-zv:]+)([1-5])$", re.IGNORECASE)
_NUMERAL_CHARS = set("零〇一二三四五六七八九十百千万亿两")


def numeric_to_marks(syllable: str) -> str:
    """'hao3' -> 'hǎo', 'lv4' -> 'lǜ', 'le5' -> 'le'. Non-pinyin passes through."""
    m = _SYLLABLE_RE.match(syllable.replace("ü", "v").replace("Ü", "V"))
    if not m:
        return syllable
    body, tone = m.group(1).replace("u:", "v"), int(m.group(2))
    if tone == 5:
        return body.replace("v", "ü")
    lower = body.lower()
    # Placement: a or e takes the mark; in "ou" the o does; otherwise the last vowel.
    if "a" in lower:
        idx = lower.index("a")
    elif "e" in lower:
        idx = lower.index("e")
    elif "ou" in lower:
        idx = lower.index("o")
    else:
        idx = max(lower.rfind(v) for v in "iouv")
        if idx < 0:
            return body
    marked = _TONE_MARKS[lower[idx]][tone - 1]
    if body[idx].isupper():
        marked = marked.upper()
    return (body[:idx] + marked + body[idx + 1 :]).replace("v", "ü")


def tone_of(syllable: str) -> int | None:
    m = _SYLLABLE_RE.match(syllable)
    return int(m.group(2)) if m else None


def _with_tone(syllable: str, tone: int) -> str:
    m = _SYLLABLE_RE.match(syllable)
    return f"{m.group(1)}{tone}" if m else syllable


def citation_syllables(word: str) -> list[str]:
    """Citation-tone numeric pinyin for each character of a word."""
    out = lazy_pinyin(word, style=Style.TONE3, neutral_tone_with_five=True, errors=lambda s: list(s))
    if len(out) != len(word):  # non-CJK runs; keep 1:1 with characters
        out = [
            lazy_pinyin(ch, style=Style.TONE3, neutral_tone_with_five=True, errors=lambda s: [s])[0]
            for ch in word
        ]
    fixed = []
    for ch, syl in zip(word, out):
        if ch == "一" and tone_of(syl) in (1, 2, 4):
            syl = "yi1"
        elif ch == "不" and tone_of(syl) in (2, 4):
            syl = "bu4"
        fixed.append(syl)
    return fixed


def apply_sandhi(words: list[tuple[str, list[str]]]) -> list[list[str]]:
    """Given [(word, citation_syllables)] for one phrase (no punctuation inside),
    return surface syllables per word."""
    surface = [list(syls) for _, syls in words]
    chars = [list(w) for w, _ in words]
    flat = [(wi, si) for wi, syls in enumerate(surface) for si in range(len(syls))]

    def nxt(k):
        return flat[k + 1] if k + 1 < len(flat) else None

    def prev(k):
        return flat[k - 1] if k > 0 else None

    # 1-2. 一 and 不, using citation tone of the following syllable.
    for k, (wi, si) in enumerate(flat):
        ch = chars[wi][si]
        if ch not in ("一", "不"):
            continue
        n = nxt(k)
        next_tone = tone_of(words[n[0]][1][n[1]]) if n else None
        next_char = chars[n[0]][n[1]] if n else None
        if ch == "不":
            if next_tone == 4:
                surface[wi][si] = "bu2"
            continue
        p = prev(k)
        prev_char = chars[p[0]][p[1]] if p else None
        is_number = (
            n is None
            or prev_char == "第"
            or (prev_char in _NUMERAL_CHARS)
            or (next_char in _NUMERAL_CHARS)
            or (next_char is not None and next_char.isdigit())
        )
        if is_number or next_tone is None or next_tone == 5:
            continue
        surface[wi][si] = "yi2" if next_tone == 4 else "yi4"

    # 3a. Third-tone runs inside a word: all but the last become tone 2.
    for wi, syls in enumerate(surface):
        for si in range(len(syls) - 1):
            if tone_of(syls[si]) == 3 and tone_of(syls[si + 1]) == 3:
                syls[si] = _with_tone(syls[si], 2)

    # 3b. Across word boundaries, right to left.
    for wi in range(len(surface) - 2, -1, -1):
        if not surface[wi] or not surface[wi + 1]:
            continue
        if tone_of(surface[wi][-1]) == 3 and tone_of(surface[wi + 1][0]) == 3:
            surface[wi][-1] = _with_tone(surface[wi][-1], 2)
            # re-run the in-word rule leftwards for this word
            syls = surface[wi]
            for si in range(len(syls) - 2, -1, -1):
                if tone_of(syls[si]) == 3 and tone_of(syls[si + 1]) == 3:
                    syls[si] = _with_tone(syls[si], 2)
    return surface
