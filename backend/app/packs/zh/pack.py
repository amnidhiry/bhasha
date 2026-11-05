import logging
import re
from collections.abc import Iterable
from pathlib import Path

import jieba
import jieba.posseg

from app.packs.base import NUMBER, OTHER, PROPER, PUNCT, WORD, LanguagePack, LevelFramework, PromptProfile, Syllable, Token
from app.packs.zh.pinyin import apply_sandhi, citation_syllables, numeric_to_marks
from app.packs.zh.polyphones import context_reading

jieba.setLogLevel(logging.WARNING)

_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_LATIN = re.compile(r"[A-Za-z]")
_HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f]")
_LATIN_WORD = re.compile(r"[A-Za-zÀ-ɏ]+")
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
    bcp47 = "zh-CN"
    default_facets = ("meaning", "reading")
    facets = frozenset({"meaning", "reading", "listening", "tone", "production", "cloze"})
    sentence_joiner = ""
    terminators = "。！？!?…"
    max_cloze_len = 12
    features = frozenset({"bootcamp", "handwriting", "characters", "tonecheck"})
    reading_aid = "pinyin"
    script_unit = "characters"
    accept_language = "zh-CN,zh;q=0.9,en;q=0.5"
    sentences_title = "例句"
    grammar_search = "https://resources.allsetlearning.com/chinese/grammar/Special:Search?search="
    attribution = "CC-CEDICT (CC BY-SA 4.0); Make Me a Hanzi; complete-hsk-vocabulary (MIT); SUBTLEX-CH; Tatoeba (CC BY 2.0 FR)"
    adjective = "Chinese"
    native_name = "中文"
    starter = ("我的家 · My family",
               "我叫小明。我是学生。我家有四口人：爸爸、妈妈、姐姐和我。爸爸是医生，妈妈是老师。姐姐在北京工作。我很喜欢我的家。")
    tab_glyphs = {"library": "读", "review": "复", "journal": "写", "sounds": "音", "progress": "进"}
    subtitle_words = ("chinese", "中文", "简体", "繁體", "繁体", "mandarin", "chs", "cht")
    subtitle_codes = frozenset({"zh", "chi", "zho", "cmn", "zh-cn", "zh-hans", "zh-tw", "zh-hant", "zh-hk", "yue"})
    prompts = PromptProfile(
        language_name="Mandarin Chinese (Simplified)",
        learner_note="Write Simplified characters.",
        list_joiner="、",
        dialogue_rule="a natural dialogue between two people, each line starting with the speaker's name and a full-width colon (e.g. 小明：)",
        error_categories={
            "word_choice": "Word choice", "measure_word": "Measure word", "word_order": "Word order",
            "aspect_particle": "了 / 过 / 着", "missing_word": "Missing word", "extra_word": "Extra word",
            "wrong_character": "Wrong character", "grammar": "Grammar",
        },
        no_reading_aid_rule="Never write pinyin or tone marks; the app shows pronunciation itself.",
    )

    @property
    def levels(self) -> LevelFramework:
        from app.config import get_settings

        return LevelFramework(tag_prefix=get_settings().hsk_version, levels=[str(i) for i in range(1, 8)],
                              labels={"7": "7–9"}, name="HSK 3.0")

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


    # --- Pack hooks (see app/packs/base.py) -------------------------------------------

    def reading_display(self, reading: str) -> str:
        return " ".join(numeric_to_marks(s) for s in reading.replace("u:", "v").split())

    def in_script(self, ch: str) -> bool:
        return bool(_CJK.match(ch))

    def script_count(self, text: str) -> int:
        return len(_HAN.findall(text))

    def script_ratio(self, line: str) -> float:
        """Han characters against Han characters plus Latin words: 我用iPhone is
        Chinese (2 of 3), "Hello world" is not. Lines with neither score 0."""
        han = self.script_count(line)
        latin = len(_LATIN_WORD.findall(line))
        return han / (han + latin) if han + latin else 0.0

    def covered(self, word: str, allowed: set[str]) -> bool:
        """In bounds if allowed, or if it splits into allowed words (jieba often merges
        很好 or 我们的 into one token)."""
        if word in allowed:
            return True
        n = len(word)
        ok = [True] + [False] * n
        for i in range(1, n + 1):
            for j in range(max(0, i - 6), i):
                if ok[j] and word[j:i] in allowed:
                    ok[i] = True
                    break
        return ok[n]

    def error_unit_words(self, category: str, words: list[str]) -> list[str]:
        if category == "aspect_particle":
            return [w for w in words if w in ("了", "过", "着")] or words
        if category == "measure_word":
            return [w for w in words if len(w) == 1] or words
        return words

    def scenarios(self) -> list:
        from app.packs.zh.scenarios import SCENARIOS

        return SCENARIOS

    def meanings(self, db, unit) -> list[str]:
        """HSK meanings, then Make Me a Hanzi for characters, then CC-CEDICT by reading."""
        from sqlalchemy import select

        from app.models import CedictEntry, CharacterInfo

        m = (unit.extra or {}).get("meanings")
        if m:
            return m
        if unit.type == "character":
            info = db.get(CharacterInfo, unit.headword)
            if info is not None and info.definition:
                return [info.definition]
        entries = list(db.scalars(select(CedictEntry).where(CedictEntry.simplified == unit.headword)))
        exact = [e for e in entries if e.pinyin.lower().replace("u:", "v") == unit.reading]
        return [g for e in (exact or entries) for g in e.glosses][:6]

    def lookup_extras(self, db, word: str) -> dict:
        from sqlalchemy import select

        from app.models import CedictEntry, CharacterInfo
        from app.packs.zh.pinyin import apply_sandhi

        cite = self.citation(word)
        surf = apply_sandhi([(word, cite)])[0]
        cedict = list(db.scalars(select(CedictEntry).where(CedictEntry.simplified == word)))
        chars = {c.character: c for c in db.scalars(select(CharacterInfo).where(CharacterInfo.character.in_(set(word))))}
        return {
            "reading": {"citation": " ".join(cite), "citation_display": " ".join(numeric_to_marks(s) for s in cite),
                        "surface_display": " ".join(numeric_to_marks(s) for s in surf)},
            "cedict": [{"traditional": e.traditional, "pinyin": e.pinyin, "pinyin_display": self.reading_display(e.pinyin),
                        "glosses": e.glosses} for e in cedict],
            "characters": [
                {"character": ch, "definition": chars[ch].definition, "pinyin": chars[ch].pinyin,
                 "decomposition": chars[ch].decomposition, "radical": chars[ch].radical,
                 "etymology": chars[ch].etymology} if ch in chars else {"character": ch}
                for ch in self.sub_units(word)
            ],
            "attribution": self.attribution,
        }
