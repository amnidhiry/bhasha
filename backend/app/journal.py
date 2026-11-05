"""Journal: you write, the model corrects, code checks, mistakes become cards.

The model returns per sentence a minimal correction, an English translation
and categorized errors with one-line explanations. Code then verifies every
error against your text (the wrong span must be in what you wrote, the right
span in the correction) and drops what doesn't check out, so a hallucinated
"error" never becomes a card. Each verified error with something to fill in
becomes a cloze card on the word it's about.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import gateway
from app.models import Card, ErrorItem, JournalEntry, Unit
from app.packs import get_pack
from app.packs.base import WORD
from app.packs.zh.pinyin import citation_syllables

CATEGORIES = {
    "word_choice": "Word choice",
    "measure_word": "Measure word",
    "word_order": "Word order",
    "aspect_particle": "了 / 过 / 着",
    "missing_word": "Missing word",
    "extra_word": "Extra word",
    "wrong_character": "Wrong character",
    "grammar": "Grammar",
}
ASPECT = {"了", "过", "着"}
MAX_CLOZE_CHARS = 12

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sentences", "comment"],
    "properties": {
        "comment": {"type": "string"},
        "sentences": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["original", "corrected", "english", "errors"],
                "properties": {
                    "original": {"type": "string"},
                    "corrected": {"type": "string"},
                    "english": {"type": "string"},
                    "errors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["category", "wrong", "right", "explanation"],
                            "properties": {
                                "category": {"type": "string", "enum": list(CATEGORIES)},
                                "wrong": {"type": "string"},
                                "right": {"type": "string"},
                                "explanation": {"type": "string"},
                            },
                        },
                    },
                },
            },
        },
    },
}

SYSTEM = """You correct short journal entries written in Mandarin (Simplified) by a native English speaker who is a beginner (around HSK {level}).

For each sentence they wrote, in order:
- "original": the sentence exactly as written.
- "corrected": the smallest change that makes it correct and natural, keeping their meaning and their words where possible. If it's already fine, repeat it unchanged.
- "english": a natural English translation of the corrected sentence.
- "errors": one item per mistake, [] if none. "wrong" is the exact text from the original ("" if something was missing); "right" is the exact replacement text in the corrected sentence ("" if something should be deleted). Keep both as short as possible. "explanation" is one short English sentence a beginner understands; avoid jargon or gloss it. Categories: {categories}.

Don't flag punctuation-only or full-width/half-width differences, and don't rewrite for style. "comment" is one or two encouraging English sentences on the entry overall, naming the one thing most worth practising next."""


def writing_prompt(db: Session, user_id: int) -> dict:
    """Words to try using (recently mined or due soon) and an idea, rotating daily."""
    from app.generator import _auto_targets

    ideas = [
        "What did you eat today?", "Describe someone in your family.", "What are you doing this weekend?",
        "Describe where you live.", "What did you do yesterday?", "Talk about a friend.",
        "What's the weather like, and what will you do?", "Describe your work or studies.",
        "Something you bought recently.", "A place you'd like to visit.",
    ]
    return {"words": _auto_targets(db, user_id, limit=5), "idea": ideas[date.today().toordinal() % len(ideas)]}


def _level(db: Session, user_id: int) -> str:
    from app.generator import _hsk_level_pool
    from app.learner import known_unit_ids

    known = {h for (h,) in db.execute(select(Unit.headword).where(Unit.id.in_(known_unit_ids(db, user_id, "zh"))))}
    return _hsk_level_pool(db, known)[0]


def _unit_for(db: Session, right: str, category: str) -> Unit:
    """The unit an error is about: the particle for aspect errors, the measure word for
    classifier errors, else the first word of the fix that's already a unit."""
    words = [t.surface for t in get_pack("zh").analyze(right) if t.kind == WORD]
    if category == "aspect_particle":
        words = [w for w in words if w in ASPECT] or words
    elif category == "measure_word":
        words = [w for w in words if len(w) == 1] or words
    for w in words:
        unit = db.scalar(select(Unit).where(Unit.language == "zh", Unit.type == "word", Unit.headword == w)
                         .order_by(Unit.id))
        if unit is not None:
            return unit
    head = right[:64]
    unit = db.scalar(select(Unit).where(Unit.language == "zh", Unit.type == "phrase", Unit.headword == head))
    if unit is None:
        unit = Unit(language="zh", type="phrase", headword=head, reading=" ".join(citation_syllables(head)),
                    level_tags=[], track_tags=[], extra={"source": "journal"})
        db.add(unit)
        db.flush()
    return unit


def apply_correction(db: Session, entry: JournalEntry, data: dict) -> list[ErrorItem]:
    sentences, items = [], []
    for i, s in enumerate(data.get("sentences") or []):
        original, corrected = str(s.get("original", "")).strip(), str(s.get("corrected", "")).strip()
        if not original:
            continue
        corrected = corrected or original
        sentences.append({"original": original, "corrected": corrected, "english": str(s.get("english", "")).strip()})
        if corrected == original:
            continue  # the model listed errors but changed nothing: trust the text, not the list
        for e in s.get("errors") or []:
            cat = e.get("category") if e.get("category") in CATEGORIES else "grammar"
            wrong, right = str(e.get("wrong", "")).strip(), str(e.get("right", "")).strip()
            if (wrong and wrong not in original) or (right and right not in corrected) or (not wrong and not right) \
                    or wrong == right:
                continue
            item = ErrorItem(entry_id=entry.id, user_id=entry.user_id, category=cat, wrong=wrong[:128],
                             right=right[:128], explanation=str(e.get("explanation", "")).strip()[:500],
                             sentence_index=len(sentences) - 1)
            db.add(item)
            db.flush()
            if right and len(right) <= MAX_CLOZE_CHARS:
                unit = _unit_for(db, right, cat)
                item.unit_id = unit.id
                card = Card(user_id=entry.user_id, unit_id=unit.id, facet=f"cloze:{item.id}",
                            due=datetime.now(timezone.utc), context_sentence=corrected,
                            cloze={"sentence": corrected, "answer": right, "wrong": wrong, "category": cat,
                                   "explanation": item.explanation, "english": sentences[-1]["english"]})
                db.add(card)
                db.flush()
                item.card_id = card.id
            items.append(item)
    entry.sentences = sentences
    entry.corrected = "".join(s["corrected"] for s in sentences)
    entry.comment = str(data.get("comment", "")).strip() or None
    entry.status = "done"
    db.commit()
    return items


def correct(db: Session, entry: JournalEntry) -> list[ErrorItem]:
    if entry.status == "done":
        return []
    system = SYSTEM.format(level=_level(db, entry.user_id),
                           categories=", ".join(f"{k} ({v})" for k, v in CATEGORIES.items()))
    data = gateway.complete_json(db, "journal", system, entry.text, SCHEMA, user_id=entry.user_id,
                                 cache_key=f"bhasha-journal-{entry.user_id}").data
    return apply_correction(db, entry, data)


def category_counts(db: Session, user_id: int, days: int = 30) -> dict[str, int]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    counts: dict[str, int] = {}
    for (cat,) in db.execute(select(ErrorItem.category).where(ErrorItem.user_id == user_id, ErrorItem.created_at >= since)):
        counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
