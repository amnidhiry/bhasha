"""Graded reader generation: the model writes, deterministic code checks.

1. Brief: known words, an HSK "level pool" of in-level new words, up to five
   target words (due soon or recently mined), topic, genre and length.
2. Generate structured JSON: sentences with English, target words used,
   comprehension questions.
3. Validate with the language pack: every word must be known, a target, or
   from the level pool, and the number of distinct new words is capped.
4. Repair: up to two rewrites naming the exact words to replace; then accept
   and record that it fell short.
5. Store as a generated text. Reading aids (pinyin, romanization), glosses and
   coverage come from local data in the reader, never from the model.

The level pool lets a beginner with almost no known words still get a text:
its new words come from the lowest level (HSK, or the pack's own framework)
not yet mostly known.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner import known_unit_ids
from app.llm import gateway
from app.models import Card, Text, Unit
from app.packs import get_pack
from app.packs.base import WORD
from app.reader import create_text, sentence_map

GENRES = {
    "story": "a short story with a clear beginning, middle and end",
    "dialogue": None,  # the pack's dialogue rule
    "news": "a short, simple news-style report",
    "everyday": "a practical everyday situation (shopping, ordering food, directions, phone calls)",
}
LENGTHS = {"short": 6, "medium": 10, "long": 16}
MAX_REPAIRS = 2
MAX_KNOWN_IN_PROMPT = 2500
MAX_POOL_IN_PROMPT = 600

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "title_en", "sentences", "target_words_used", "questions"],
    "properties": {
        "title": {"type": "string"},
        "title_en": {"type": "string"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["text", "en"],
                "properties": {"text": {"type": "string"}, "en": {"type": "string"}},
            },
        },
        "target_words_used": {"type": "array", "items": {"type": "string"}},
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["question", "question_en", "answer_en"],
                "properties": {
                    "question": {"type": "string"},
                    "question_en": {"type": "string"},
                    "answer_en": {"type": "string"},
                },
            },
        },
    },
}

SYSTEM = """You write graded readers in {language} for a native English speaker.

Rules:
- Write natural, idiomatic {language} a native speaker would actually say. Short sentences. {no_aid}
- Use ONLY words from KNOWN WORDS and TARGET WORDS, plus at most {max_new} distinct words from LEVEL WORDS.
  Names of people and places, and numbers, are fine. Prefer rewording over using any other word.
- Use every TARGET WORD at least once, in a context that makes its meaning guessable, and reuse it if natural.
- Every sentence ends with one of {terminators} Give each sentence a natural English translation (not word-for-word).
- Write 3 comprehension questions in {language} using the same vocabulary, with English versions and short English answers.
- target_words_used lists the target words that appear in the text.
{note}
KNOWN WORDS ({n_known}):
{known}

LEVEL WORDS (new to the learner, {framework} {level}):
{pool}
"""


@dataclass
class Brief:
    language: str
    topic: str
    genre: str
    sentences: int
    known: list[str]
    pool: list[str]
    level: str
    targets: list[str]
    max_new: int


@dataclass
class Check:
    out_of_bounds: list[str] = field(default_factory=list)
    new_words: list[str] = field(default_factory=list)
    missing_targets: list[str] = field(default_factory=list)
    too_many_new: bool = False

    @property
    def ok(self) -> bool:
        return not self.out_of_bounds and not self.too_many_new


def _level_pool(db: Session, language: str, known_heads: set[str]) -> tuple[str, list[str]]:
    """Cumulative words up to the lowest level that is under 80% known."""
    fw = get_pack(language).levels
    order = {lvl: i for i, lvl in enumerate(fw.levels)}
    by_level: dict[str, list[tuple[int, str]]] = {}
    for u in db.scalars(select(Unit).where(Unit.language == language, Unit.type == "word")):
        for tag in u.level_tags or []:
            v, _, lvl = tag.partition(":")
            if v == fw.tag_prefix and lvl in order:
                by_level.setdefault(lvl, []).append((u.frequency_rank or 10**9, u.headword))
    pool: list[str] = []
    cumulative: set[str] = set()
    level = fw.label(fw.levels[0]) if fw.levels else "1"
    for lvl in sorted(by_level, key=order.__getitem__):
        heads = {h for _, h in by_level[lvl]}
        cumulative |= heads
        level = fw.label(lvl)
        if len(cumulative & known_heads) < 0.8 * len(cumulative):
            break
    ranked = sorted({(r, h) for lvl_words in by_level.values() for r, h in lvl_words if h in cumulative})
    seen: set[str] = set()
    for _, h in ranked:
        if h not in known_heads and h not in seen:
            seen.add(h)
            pool.append(h)
    return level, pool


def _auto_targets(db: Session, user_id: int, language: str, limit: int = 5) -> list[str]:
    """Recently mined or soon-due meaning cards: recycled into new texts."""
    soon = datetime.now(timezone.utc) + timedelta(days=2)
    cards = db.scalars(
        select(Card).join(Unit, Card.unit_id == Unit.id)
        .where(Card.user_id == user_id, Card.facet == "meaning", ~Card.suspended, Unit.language == language)
        .order_by(Card.created_at.desc()).limit(50)
    )
    picked: list[str] = []
    for c in sorted(cards, key=lambda c: (c.due.replace(tzinfo=c.due.tzinfo or timezone.utc) > soon, -c.id)):
        if c.unit.headword not in picked:
            picked.append(c.unit.headword)
        if len(picked) == limit:
            break
    return picked


def build_brief(db: Session, user_id: int, topic: str, genre: str, length: str,
                targets: list[str] | None = None, language: str = "zh") -> Brief:
    known_ids = known_unit_ids(db, user_id, language)
    rows = db.execute(select(Unit.headword, Unit.frequency_rank).where(Unit.id.in_(known_ids))).all() if known_ids else []
    known = [h for h, _ in sorted({(h, r or 10**9) for h, r in rows}, key=lambda x: x[1])][:MAX_KNOWN_IN_PROMPT]
    level, pool = _level_pool(db, language, set(known))
    n = LENGTHS.get(length, LENGTHS["medium"])
    chosen = [t.strip() for t in (targets or []) if t.strip()][:5] or _auto_targets(db, user_id, language)
    # Beginners have few known words, so allow more level words; later, keep new words scarce.
    max_new = max(8, n) if len(known) < 150 else max(2, math.ceil(n * 0.4))
    return Brief(language=language, topic=topic.strip() or "daily life", genre=genre if genre in GENRES else "story", sentences=n,
                 known=known, pool=pool[:MAX_POOL_IN_PROMPT], level=level, targets=chosen, max_new=max_new)


def _covered(word: str, allowed: set[str], language: str = "zh") -> bool:
    """Is a token's head inside the allowed vocabulary? (The pack decides: zh
    accepts tokens that split into allowed words.)"""
    return get_pack(language).covered(word, allowed)


def check(brief: Brief, sentences: list[str]) -> Check:
    pack = get_pack(brief.language)
    known = set(brief.known) | set(brief.targets)
    allowed = known | set(brief.pool)
    result = Check()
    new: set[str] = set()
    body = pack.sentence_joiner.join(sentences)
    for tok in pack.analyze(body):
        if tok.kind != WORD:
            continue
        if not pack.covered(tok.head, allowed):
            if tok.head not in result.out_of_bounds:
                result.out_of_bounds.append(tok.head)
        elif not pack.covered(tok.head, known):
            new.add(tok.head)
    result.new_words = sorted(new)
    result.too_many_new = len(new) > brief.max_new
    result.missing_targets = [t for t in brief.targets if t not in body]
    return result


def _genre(brief: Brief) -> str:
    return GENRES[brief.genre] or get_pack(brief.language).prompts.dialogue_rule


def _user_prompt(brief: Brief) -> str:
    j = get_pack(brief.language).prompts.list_joiner
    targets = j.join(brief.targets) if brief.targets else "(none)"
    return (f"Write {_genre(brief)} about: {brief.topic}\n"
            f"Length: about {brief.sentences} sentences.\n"
            f"TARGET WORDS: {targets}")


def _repair_prompt(brief: Brief, previous: dict, problem: Check) -> str:
    j = get_pack(brief.language).prompts.list_joiner
    lines = [_user_prompt(brief), "", "Your previous version:", str(previous), "", "Rewrite it to fix these problems:"]
    if problem.out_of_bounds:
        lines.append("- Replace these words, which the learner doesn't know and aren't allowed: "
                     + j.join(problem.out_of_bounds) + ". Use known words or reword.")
    if problem.too_many_new:
        lines.append(f"- Use at most {brief.max_new} distinct LEVEL WORDS; you used {len(problem.new_words)}: "
                     + j.join(problem.new_words) + ". Keep the most useful ones.")
    if problem.missing_targets:
        lines.append("- Include these target words: " + j.join(problem.missing_targets))
    lines.append("Keep the same topic, length and JSON format.")
    return "\n".join(lines)


def _clean(data: dict, language: str = "zh") -> list[dict]:
    pack = get_pack(language)
    out = []
    for s in data.get("sentences") or []:
        body = str(s.get("text", "")).strip()
        if not body:
            continue
        if body[-1] not in pack.terminators and not body.endswith(("”", "」", '"')):
            body += pack.terminators[0]
        out.append({"text": body, "en": str(s.get("en", "")).strip()})
    return out


def system_prompt(brief: Brief) -> str:
    pack = get_pack(brief.language)
    pr, j = pack.prompts, pack.prompts.list_joiner
    return SYSTEM.format(language=pr.language_name, no_aid=pr.no_reading_aid_rule,
                         terminators=" ".join(pack.terminators[:3]), note=(pr.learner_note + "\n") if pr.learner_note else "",
                         max_new=brief.max_new, n_known=len(brief.known),
                         known=j.join(brief.known) or "(none yet: the learner is a beginner)",
                         framework=pack.levels.name or "level", level=brief.level, pool=j.join(brief.pool) or "(none)")


def generate(db: Session, user_id: int, topic: str, genre: str = "story", length: str = "medium",
             targets: list[str] | None = None, language: str = "zh") -> Text:
    pack = get_pack(language)
    brief = build_brief(db, user_id, topic, genre, length, targets, language)
    system = system_prompt(brief)
    # The word lists lead the prompt, so a stable cache key lets the provider reuse them.
    cache_key = f"bhasha-gen-{language}-{user_id}-{len(brief.known)}-{brief.level}"
    prompt = _user_prompt(brief)
    attempts = []
    data: dict = {}
    sentences: list[dict] = []
    result = Check()
    for attempt in range(MAX_REPAIRS + 1):
        data = gateway.complete_json(db, "generate", system, prompt, SCHEMA, user_id=user_id, cache_key=cache_key).data
        sentences = _clean(data, language)
        result = check(brief, [s["text"] for s in sentences])
        attempts.append({"out_of_bounds": result.out_of_bounds, "new_words": result.new_words,
                         "missing_targets": result.missing_targets})
        if result.ok and sentences:
            break
        prompt = _repair_prompt(brief, data, result)
    if not sentences:
        from app.llm.errors import LlmError
        raise LlmError("The model returned no sentences.")

    title = str(data.get("title") or brief.topic)[:200]
    body = pack.sentence_joiner.join(s["text"] for s in sentences)
    text = create_text(db, user_id, language, title, body, provenance="generated")
    text.meta = {
        "title_en": str(data.get("title_en") or ""),
        "sentences": sentences,
        "sentence_map": sentence_map([s["text"] for s in sentences], language),
        "questions": data.get("questions") or [],
        "targets": brief.targets,
        "target_words_used": data.get("target_words_used") or [],
        "level": brief.level,
        "genre": brief.genre,
        "topic": brief.topic,
        "new_words": result.new_words,
        "accepted_with_issues": not result.ok,
        "out_of_bounds": result.out_of_bounds,
        "attempts": len(attempts),
        "flags": [],
    }
    db.commit()
    return text
