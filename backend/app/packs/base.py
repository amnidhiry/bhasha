"""The language-pack interface. The core (scheduler, reader, coverage, generator,
journal, tutor, lookup, progress) only talks to this, so Bengali or Arabic plugs in
without core changes. Defaults suit a space-delimited language; the Mandarin pack
overrides what differs. See docs/bengali.md, "Pack design"."""

import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field



def words(text: str) -> list[str]:
    """Runs of letters and combining marks. (`\\w` would split আমি at its vowel
    sign, a combining mark, so this goes by Unicode category instead.)"""
    out, cur = [], []
    for ch in text:
        if unicodedata.category(ch)[0] in "LM" or ch in "\u200c\u200d":  # ZWNJ/ZWJ inside Bengali words
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


# Token kinds. Only WORD tokens count toward coverage.
WORD = "word"
PROPER = "proper"
NUMBER = "number"
PUNCT = "punct"
OTHER = "other"


@dataclass
class Syllable:
    """One part of a word's reading aid. zh: one character with citation vs spoken
    tone (sandhi). bn: the whole word, letter-by-letter vs as said, plus "traps"
    (spans where the sound departs from the letters)."""

    text: str  # the written span
    citation: str  # canonical stored form, e.g. "bu4"
    surface: str  # as spoken, e.g. "bu2"
    citation_display: str  # e.g. "bù"
    surface_display: str  # e.g. "bú"
    traps: list = field(default_factory=list)  # [(start, end, kind)] within `text`
    extra: dict = field(default_factory=dict)  # pack-specific, e.g. {"tone": 2}


ReadingPart = Syllable  # the language-neutral name


@dataclass
class Morph:
    segment: str  # e.g. "কে"
    grammar_key: str | None = None  # links to a grammar unit, e.g. "bn-gram:case-ke"
    features: dict = field(default_factory=dict)


@dataclass
class Token:
    surface: str
    kind: str
    sentence_index: int
    syllables: list[Syllable] = field(default_factory=list)
    lemma: str | None = None  # dictionary form when it differs from the surface (bn); None for zh
    morph: list[Morph] = field(default_factory=list)

    @property
    def counts_for_coverage(self) -> bool:
        return self.kind == WORD

    @property
    def head(self) -> str:
        """What the token is learned as: the lemma when there is one."""
        return self.lemma or self.surface


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    title_native: str  # the title in the target language
    setting: str        # English, for the learner
    tutor_role: str     # who the tutor plays
    goal: str           # what the learner must achieve
    twist: str          # a complication the tutor introduces
    phrases: tuple[str, ...] = field(default_factory=tuple)  # key phrases the tutor may use
    level: str = "1"


@dataclass
class LevelFramework:
    tag_prefix: str  # "hsk3-2025" | "bn-freq-2026"
    levels: list[str]  # ["1".."7"] | ["A1", "A2", "B1", "B2"]
    labels: dict[str, str] = field(default_factory=dict)  # "7" -> "HSK 7–9"
    name: str = ""  # "HSK 3.0" shown in progress

    def label(self, level: str) -> str:
        return self.labels.get(level, level)


@dataclass
class PromptProfile:
    language_name: str  # "Mandarin Chinese (Simplified)"
    learner_note: str = ""  # appended to system prompts: register, script, regional rules
    list_joiner: str = ", "
    dialogue_rule: str = "a natural dialogue between two people, each line starting with the speaker's name and a colon"
    error_categories: dict[str, str] = field(default_factory=dict)
    no_reading_aid_rule: str = "Never write a romanization or reading aid; the app shows pronunciation itself."


class LanguagePack(ABC):
    code: str
    name: str
    bcp47: str = "und"  # lang attribute and device voice, e.g. "zh-CN", "bn-IN"
    # Facets created by default when a word is mined, and all facets the pack supports.
    default_facets: tuple[str, ...] = ("meaning", "reading")
    facets: frozenset[str] = frozenset({"meaning", "reading", "listening", "production", "cloze"})
    sentence_joiner: str = " "
    terminators: str = ".!?"
    max_cloze_len: int = 24  # code points
    # Pack features the PWA shows: "bootcamp", "handwriting", "characters", "tonecheck".
    features: frozenset[str] = frozenset()
    reading_aid: str = "romanization"  # "pinyin" | "romanization": how the PWA labels and colours it
    accept_language: str = "en"
    subtitle_codes: frozenset[str] = frozenset()  # media-server language codes for this language
    subtitle_words: tuple[str, ...] = ()  # words in a track title that mean this language
    adjective: str = ""  # "Chinese", "Bengali": for messages ("no Chinese lines")
    native_name: str = ""  # "中文", "বাংলা"
    starter: tuple[str, str] | None = None  # (title, body): the first text a new learner can open
    tab_glyphs: dict[str, str] = {}  # PWA tab icons in the script, e.g. {"library": "读"}
    levels: LevelFramework
    prompts: PromptProfile

    def normalize(self, text: str) -> str:
        return text

    @abstractmethod
    def analyze(self, text: str) -> list[Token]:
        """Segment text into tokens with reading aids."""

    @abstractmethod
    def reading(self, word: str) -> str:
        """Canonical stored reading for a word (zh: citation numeric pinyin)."""

    def reading_display(self, reading: str) -> str:
        """How a stored reading is shown (zh: numeric pinyin -> tone marks)."""
        return reading

    def unit_key(self, tok: Token) -> tuple[str, str, str]:
        """(unit type, headword, reading) a word token is learned as."""
        reading = " ".join(s.citation for s in tok.syllables) or self.reading(tok.head)
        return ("word", tok.head, reading)

    @abstractmethod
    def sub_units(self, word: str) -> list[str]:
        """Sub-word units a word is built from (zh: characters; bn: letters/conjuncts)."""

    def covered(self, word: str, allowed: set[str]) -> bool:
        """Is this word (a token's head) inside the allowed vocabulary?"""
        return word in allowed

    script_unit: str = "words"

    def script_count(self, text: str) -> int:
        """Size of a text as learners count it ("3,400 characters", "620 words")."""
        return sum(1 for w in words(text) if any(self.in_script(c) for c in w))

    def script_ratio(self, line: str) -> float:
        """Share of a line's words in this language's script (importer language detection)."""
        runs = words(line)
        return 0.0 if not runs else sum(1 for w in runs if any(self.in_script(c) for c in w)) / len(runs)

    def in_script(self, ch: str) -> bool:
        return ch.isalpha()

    def lint(self, tokens: list[Token]) -> list[dict]:
        """Register/regional problems in model output (bn: sadhu forms, Dhaka words)."""
        return []

    def meanings(self, db, unit) -> list[str]:
        """Glosses for a unit, beyond what's stored on the unit itself."""
        from sqlalchemy import select

        from app.models import DictionaryEntry

        m = (unit.extra or {}).get("meanings")
        if m:
            return m
        rows = db.scalars(select(DictionaryEntry).where(DictionaryEntry.language == self.code,
                                                        DictionaryEntry.headword == unit.headword))
        return [g for e in rows for g in (e.glosses or [])][:6]

    def lookup_extras(self, db, word: str) -> dict:
        """Lookup sections beyond units (zh: CC-CEDICT, characters, spoken/written tones).
        The default: the word's reading and its dictionary entries."""
        from sqlalchemy import select

        from app.models import DictionaryEntry

        r = self.reading(word)
        rows = db.scalars(select(DictionaryEntry).where(DictionaryEntry.language == self.code,
                                                        DictionaryEntry.headword == word).order_by(DictionaryEntry.id))
        return {
            "reading": {"citation": r, "citation_display": self.reading_display(r), "surface_display": self.reading_display(r)},
            "dictionary": [{"reading": e.reading, "reading_display": self.reading_display(e.reading) if e.reading else "",
                            "pos": e.pos, "glosses": e.glosses, "tags": e.tags, "source": e.source} for e in rows],
            "attribution": self.attribution,
        }

    attribution: str = ""
    sentences_title: str = ""  # native word for "example sentences" (zh: 例句)
    grammar_search: str = ""  # a grammar reference's search URL prefix; we link, never copy

    def error_unit_words(self, category: str, words: list[str]) -> list[str]:
        """Which words of a correction a journal error is about (zh: the particle for 了 errors)."""
        return words

    def scenarios(self) -> list:
        """Tutor role-play scenarios (app.tutor.Scenario)."""
        return []

    def meta(self) -> dict:
        """What the PWA needs to render this language."""
        return {"code": self.code, "name": self.name, "adjective": self.adjective or self.name, "bcp47": self.bcp47,
                "reading_aid": self.reading_aid, "glyphs": dict(self.tab_glyphs), "native_name": self.native_name,
                "starter": {"title": self.starter[0], "body": self.starter[1]} if self.starter else None,
                "features": sorted(self.features), "sentence_joiner": self.sentence_joiner,
                "terminators": self.terminators, "script_unit": self.script_unit,
                "levels": {"name": self.levels.name, "tag_prefix": self.levels.tag_prefix,
                           "levels": self.levels.levels, "labels": self.levels.labels}}

    def add_words(self, words: Iterable[tuple[str, str | None]]) -> None:
        """Teach the tokenizer about curriculum words as (headword, reading) pairs."""
