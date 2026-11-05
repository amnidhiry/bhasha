"""Core tables. Language-specific meaning lives in `unit.type` values that a pack
defines, so Bengali conjuncts or Arabic roots fit beside Mandarin characters.

Every per-learner table carries `user_id` from day one so family use does not
need a retrofit (open question in docs/design.md)."""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Text as SAText
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AppUser(Base):
    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Language(Base):
    __tablename__ = "language"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))


class PackVersion(Base):
    """Which data sources are loaded for a language, and at which version."""

    __tablename__ = "pack_version"
    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(ForeignKey("language.code"))
    component: Mapped[str] = mapped_column(String(64))  # e.g. cc-cedict, hsk, makemeahanzi
    version: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("language", "component", "version"),)


class Unit(Base):
    """Anything a learner can know: word, character, component, phrase, grammar point, root."""

    __tablename__ = "unit"
    id: Mapped[int] = mapped_column(primary_key=True)
    language: Mapped[str] = mapped_column(ForeignKey("language.code"))
    type: Mapped[str] = mapped_column(String(32))
    headword: Mapped[str] = mapped_column(String(128))
    # Reading is stored per word, never per character (polyphones). For zh this is
    # citation-tone numeric pinyin, e.g. "yin2 hang2".
    reading: Mapped[str] = mapped_column(String(256), default="")
    traditional: Mapped[str | None] = mapped_column(String(128))
    level_tags: Mapped[list] = mapped_column(JSONType, default=list)  # e.g. ["hsk3-2025:1"]
    frequency_rank: Mapped[int | None] = mapped_column(Integer)
    register: Mapped[str | None] = mapped_column(String(16))  # lay | clinical
    track_tags: Mapped[list] = mapped_column(JSONType, default=list)  # everyday | medical
    extra: Mapped[dict] = mapped_column(JSONType, default=dict)  # classifiers, pos, decomposition...

    __table_args__ = (
        UniqueConstraint("language", "type", "headword", "reading"),
        Index("ix_unit_lookup", "language", "headword"),
    )


class UnitRelation(Base):
    __tablename__ = "unit_relation"
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"))
    child_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))  # contains | lay_equivalent | derives_from
    position: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("parent_id", "child_id", "kind", "position"),)


class CedictEntry(Base):
    """CC-CEDICT is CC BY-SA, so it lives in its own table and is attributed in the UI."""

    __tablename__ = "cedict_entry"
    id: Mapped[int] = mapped_column(primary_key=True)
    traditional: Mapped[str] = mapped_column(String(128))
    simplified: Mapped[str] = mapped_column(String(128), index=True)
    pinyin: Mapped[str] = mapped_column(String(256))  # numeric, lowercase, u: -> v
    glosses: Mapped[list] = mapped_column(JSONType)


class CharacterInfo(Base):
    """Make Me a Hanzi dictionary data (decomposition, radical, etymology)."""

    __tablename__ = "character_info"
    character: Mapped[str] = mapped_column(String(8), primary_key=True)
    definition: Mapped[str | None] = mapped_column(Text)
    pinyin: Mapped[list] = mapped_column(JSONType, default=list)
    decomposition: Mapped[str | None] = mapped_column(String(64))
    radical: Mapped[str | None] = mapped_column(String(8))
    etymology: Mapped[dict | None] = mapped_column(JSONType)


class UnitMark(Base):
    """Manual marks: words learned elsewhere, or placement-check bulk marks."""

    __tablename__ = "unit_mark"
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))  # known | ignored
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Card(Base):
    """One FSRS card per unit facet (meaning, reading, listening, tone, ...)."""

    __tablename__ = "card"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"))
    facet: Mapped[str] = mapped_column(String(32))
    state: Mapped[int] = mapped_column(Integer, default=1)  # fsrs.State: 1 learning, 2 review, 3 relearning
    step: Mapped[int | None] = mapped_column(Integer, default=0)
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    due: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_review: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    context_sentence: Mapped[str | None] = mapped_column(Text)
    source_text_id: Mapped[int | None] = mapped_column(ForeignKey("text.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    unit: Mapped[Unit] = relationship(lazy="joined")

    __table_args__ = (
        UniqueConstraint("user_id", "unit_id", "facet"),
        Index("ix_card_due", "user_id", "suspended", "due"),
    )


class ReviewLog(Base):
    """Every review, scheduled or not. The irreplaceable table: back it up.

    `id` is generated by the client so batch sync from offline clients is idempotent."""

    __tablename__ = "review_log"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    card_id: Mapped[int] = mapped_column(ForeignKey("card.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(Integer)  # 1 again, 2 hard, 3 good, 4 easy
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32), default="queue")  # queue | reader_lookup | handwriting
    scheduled: Mapped[bool] = mapped_column(Boolean, default=True)


class Text(Base):
    __tablename__ = "text"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    language: Mapped[str] = mapped_column(ForeignKey("language.code"))
    title: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    provenance: Mapped[str] = mapped_column(String(32))  # imported | generated | tatoeba
    source_url: Mapped[str | None] = mapped_column(String(1024))
    coverage_at_creation: Mapped[float | None] = mapped_column(Float)
    # Generated texts: translations, questions, target words, flags (see app/generator.py).
    meta: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    tokens: Mapped[list["TextToken"]] = relationship(
        order_by="TextToken.position", cascade="all, delete-orphan"
    )


class TextToken(Base):
    __tablename__ = "text_token"
    id: Mapped[int] = mapped_column(primary_key=True)
    text_id: Mapped[int] = mapped_column(ForeignKey("text.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    sentence_index: Mapped[int] = mapped_column(Integer)
    surface: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(16))  # word | proper | number | punct | other
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("unit.id", ondelete="SET NULL"))


class Exposure(Base):
    """A unit seen in a text. Weak evidence: never counted as a successful review."""

    __tablename__ = "exposure"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"))
    text_id: Mapped[int | None] = mapped_column(ForeignKey("text.id", ondelete="SET NULL"))
    looked_up: Mapped[bool] = mapped_column(Boolean, default=False)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_exposure_user_unit", "user_id", "unit_id"),)


class LlmCall(Base):
    __tablename__ = "llm_call"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))
    feature: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LlmConnection(Base):
    """Where model calls go. kind: chatgpt (Sign in with ChatGPT, plan usage) or
    openai_compatible (LM Studio, or an API key). One is active at a time."""

    __tablename__ = "llm_connection"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(80))
    base_url: Mapped[str] = mapped_column(String(512))
    model: Mapped[str | None] = mapped_column(String(128))
    # Encrypted JSON: a ChatGPT token set, or {"api_key": ...}. Null = signed out.
    ciphertext: Mapped[str | None] = mapped_column(SAText)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    account_email: Mapped[str | None] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Base):
    """Background work (text generation now; imports, audio and the nightly FSRS
    re-fit later). Claimed by the worker with SELECT ... FOR UPDATE SKIP LOCKED."""

    __tablename__ = "job"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | running | done | failed
    params: Mapped[dict] = mapped_column(JSONType, default=dict)
    result: Mapped[dict] = mapped_column(JSONType, default=dict)
    error: Mapped[str | None] = mapped_column(SAText)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    seen: Mapped[bool] = mapped_column(Boolean, default=False)  # the user saw the outcome
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_job_status_created", "status", "created_at"),)


class CharacterStrokes(Base):
    """Make Me a Hanzi graphics.txt (Arphic Public License): stroke outlines and
    medians, served to Hanzi Writer as-is."""

    __tablename__ = "character_strokes"
    character: Mapped[str] = mapped_column(String(8), primary_key=True)
    strokes: Mapped[list] = mapped_column(JSONType)
    medians: Mapped[list] = mapped_column(JSONType)


class DrillAttempt(Base):
    """One answer in a sound-bootcamp drill. Accuracy per drill (and per tone or
    contrast) decides what comes up more often and when a drill counts as mastered."""

    __tablename__ = "drill_attempt"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"))
    drill: Mapped[str] = mapped_column(String(48))  # tone | pair | sandhi | contrast:<id>
    item: Mapped[str] = mapped_column(String(64))   # e.g. "ma3", "你好", "zhi1|ji1"
    answer: Mapped[str] = mapped_column(String(32))
    correct: Mapped[bool] = mapped_column(Boolean)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (Index("ix_drill_user_drill_at", "user_id", "drill", "at"),)


class AudioSyllable(Base):
    """Recorded syllables (Tone Perfect, MSU): one row per syllable, tone and speaker."""

    __tablename__ = "audio_syllable"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(16), index=True)  # "ma3", "lv4"
    speaker: Mapped[str] = mapped_column(String(16))
    path: Mapped[str] = mapped_column(String(512))  # relative to BHASHA_AUDIO_DIR
    __table_args__ = (UniqueConstraint("key", "speaker"),)


class WordFrequency(Base):
    """SUBTLEX-CH-WF (Cai & Brysbaert, 2010): film-subtitle word frequencies."""

    __tablename__ = "word_frequency"
    word: Mapped[str] = mapped_column(String(64), primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, index=True)
    per_million: Mapped[float] = mapped_column(Float)
    cd_percent: Mapped[float] = mapped_column(Float)  # share of films the word appears in


class ExampleSentence(Base):
    """Human-written example sentences (Tatoeba, CC BY 2.0 FR). `id` is Tatoeba's
    sentence id, so each sentence links back to its page for attribution."""

    __tablename__ = "example_sentence"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    source: Mapped[str] = mapped_column(String(16), default="tatoeba")
    text: Mapped[str] = mapped_column(String(256))
    translation: Mapped[str] = mapped_column(SAText)
    n_words: Mapped[int] = mapped_column(Integer)
    # The rarest word's SUBTLEX rank: a cheap difficulty measure (lower is easier).
    difficulty: Mapped[int] = mapped_column(Integer, index=True)


class SentenceUnit(Base):
    __tablename__ = "sentence_unit"
    sentence_id: Mapped[int] = mapped_column(ForeignKey("example_sentence.id", ondelete="CASCADE"), primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("unit.id", ondelete="CASCADE"), primary_key=True, index=True)


class UserFsrs(Base):
    """A learner's scheduler settings. Null weights = FSRS-6 defaults; null
    retention = BHASHA_DESIRED_RETENTION."""

    __tablename__ = "user_fsrs"
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True)
    weights: Mapped[list | None] = mapped_column(JSONType)
    desired_retention: Mapped[float | None] = mapped_column(Float)
    fitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    n_reviews: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=0)  # bumps on every change


class FsrsFit(Base):
    """One optimizer run: accepted, rejected (no better on held-out cards) or skipped."""

    __tablename__ = "fsrs_fit"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))  # accepted | rejected | skipped | failed
    message: Mapped[str] = mapped_column(SAText, default="")
    n_reviews: Mapped[int] = mapped_column(Integer, default=0)
    weights: Mapped[list | None] = mapped_column(JSONType)
    metrics: Mapped[dict] = mapped_column(JSONType, default=dict)
    optimal_retention: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
