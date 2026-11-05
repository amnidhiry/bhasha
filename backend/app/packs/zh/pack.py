import logging
import re
from collections.abc import Iterable
from pathlib import Path

import jieba
import jieba.posseg

from app.packs.base import NUMBER, OTHER, PROPER, PUNCT, WORD, LanguagePack, Syllable, Token
from app.packs.zh.pinyin import apply_sandhi, citation_syllables, numeric_to_marks
from app.packs.zh.polyphones import context_reading

jieba.setLogLevel(logging.WARNING)

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_LATIN = re.compile(r"[A-Za-z]")
_NUMBER = re.compile(r"^[0-9０-９.,，%％]+$|^[零〇一二三四五六七八九十百千万亿两]{2,}$")
_SENTENCE_END = set("。！？!?；;\n")
_PROPER_FLAGS = {"nr", "nrt", "nrfg", "ns", "nt"}

SPLIT_RULES_FILE = Path(__file__).with_name("split_rules.txt")


def load_split_rules(path: Path = SPLIT_RULES_FILE) -> dict[str, list[str]]:
    """Lute-style parser exceptions: one rule per line, parts separated by '|'.
    `一个人` over-merged by jieba becomes `一|个|人` -> ["一", "个", "人"]."""
    rules: dict[str, list[str]] = {}
    if not path.exists():
        return rules
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if "|" in line:
            parts = [p for p in line.split("|") if p]
            rules["".join(parts)] = parts
    return rules


class ZhPack(LanguagePack):
    code = "zh"
    name = "Mandarin Chinese"
    default_facets = ("meaning", "reading")

    def __init__(self, split_rules: dict[str, list[str]] | None = None):
        self._tokenizer = jieba.Tokenizer()
        self._pos = jieba.posseg.POSTokenizer(self._tokenizer)
        self.split_rules = load_split_rules() if split_rules is None else split_rules
        # Dictionary readings that override pypinyin, e.g. 朋友 peng2 you5 (neutral).
        self.readings: dict[str, str] = {}

    def add_words(self, words: Iterable[tuple[str, str | None]]) -> None:
        by_word: dict[str, set[str]] = {}
        for w, reading in words:
            by_word.setdefault(w, set())
            if reading:
                by_word[w].add(reading)
        for w, readings in by_word.items():
            if len(w) > 1 and w not in self.split_rules:
                # High frequency so curriculum words win over jieba's own merges.
                self._tokenizer.add_word(w, freq=100_000)
            # Only trust a dictionary reading when the word has exactly one; for
            # polyphones (了, 行) fall back to pypinyin's context-aware choice.
            if len(readings) == 1:
                (r,) = readings
                if len(r.split()) == len(w):
                    self.readings[w] = r

    def citation(self, word: str) -> list[str]:
        if word in self.readings:
            return self.readings[word].split()
        return citation_syllables(word)

    def _segment(self, text: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for pair in self._pos.cut(text, HMM=True):
            word, flag = pair.word, pair.flag
            if word in self.split_rules:
                out.extend((p, flag) for p in self.split_rules[word])
            else:
                out.append((word, flag))
        return out

    @staticmethod
    def _kind(word: str, flag: str) -> str:
        if word.strip() == "" or not (_CJK.search(word) or _LATIN.search(word) or word.isdigit()):
            return PUNCT
        if _NUMBER.match(word):
            return NUMBER
        if not _CJK.search(word):
            return OTHER
        if flag in _PROPER_FLAGS:
            return PROPER
        return WORD

    def analyze(self, text: str) -> list[Token]:
        tokens: list[Token] = []
        sentence = 0
        phrase: list[Token] = []  # CJK tokens between punctuation, for sandhi
        flags: dict[int, str] = {}  # id(token) -> jieba part-of-speech, for polyphone rules

        def cite_at(i: int) -> list[str]:
            t = phrase[i]
            if len(t.surface) == 1:
                prev = (phrase[i - 1].surface, flags[id(phrase[i - 1])]) if i > 0 else None
                nxt = (phrase[i + 1].surface, flags[id(phrase[i + 1])]) if i + 1 < len(phrase) else None
                if r := context_reading(t.surface, prev, nxt):
                    return [r]
            return self.citation(t.surface)

        def flush():
            if not phrase:
                return
            cites = [(t.surface, cite_at(i)) for i, t in enumerate(phrase)]
            surfaces = apply_sandhi(cites)
            for t, (_, cite), surf in zip(phrase, cites, surfaces):
                t.syllables = [
                    Syllable(ch, c, s, numeric_to_marks(c), numeric_to_marks(s))
                    for ch, c, s in zip(t.surface, cite, surf)
                ]
            phrase.clear()

        for word, flag in self._segment(text):
            kind = self._kind(word, flag)
            tok = Token(surface=word, kind=kind, sentence_index=sentence)
            flags[id(tok)] = flag
            tokens.append(tok)
            if _CJK.search(word):
                phrase.append(tok)
            else:
                flush()
            if any(ch in _SENTENCE_END for ch in word):
                sentence += 1
        flush()
        return tokens

    def reading(self, word: str) -> str:
        return " ".join(self.citation(word))

    def sub_units(self, word: str) -> list[str]:
        return [ch for ch in word if _CJK.match(ch)]
