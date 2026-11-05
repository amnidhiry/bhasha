"""The language-pack interface. The core (scheduler, reader, coverage, tutor) only
talks to this, so a Bengali or Arabic pack plugs in without core changes."""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field

# Token kinds. Only WORD tokens count toward coverage.
WORD = "word"
PROPER = "proper"
NUMBER = "number"
PUNCT = "punct"
OTHER = "other"


@dataclass
class Syllable:
    """One syllable of a reading aid. For zh: citation vs surface tone (sandhi)."""

    text: str  # the written character(s)
    citation: str  # e.g. "bu4"
    surface: str  # e.g. "bu2"
    citation_display: str  # e.g. "bù"
    surface_display: str  # e.g. "bú"


@dataclass
class Token:
    surface: str
    kind: str
    sentence_index: int
    syllables: list[Syllable] = field(default_factory=list)

    @property
    def counts_for_coverage(self) -> bool:
        return self.kind == WORD


class LanguagePack(ABC):
    code: str
    name: str
    # Facets created by default when a word is mined, and facets added later.
    default_facets: tuple[str, ...] = ("meaning", "reading")

    @abstractmethod
    def analyze(self, text: str) -> list[Token]:
        """Segment text into tokens with reading aids (pinyin, diacritics...)."""

    @abstractmethod
    def reading(self, word: str) -> str:
        """Canonical stored reading for a word (zh: citation numeric pinyin)."""

    @abstractmethod
    def sub_units(self, word: str) -> list[str]:
        """Sub-word units a word is built from (zh: characters)."""

    def add_words(self, words: Iterable[tuple[str, str | None]]) -> None:
        """Teach the tokenizer about curriculum words as (headword, reading) pairs."""
