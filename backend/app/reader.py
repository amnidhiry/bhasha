"""Text pipeline: analyze with the language pack, resolve tokens to units,
compute coverage against the learner model, and serialize for the reader."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.learner import coverage, ignored_unit_ids, known_unit_ids
from app.models import Card, Text, TextToken, Unit
from app.packs import get_pack
from app.packs.base import WORD, Token

NEW, LEARNING, KNOWN, IGNORED = "new", "learning", "known", "ignored"


def resolve_units(db: Session, language: str, tokens: list[Token], create: bool = True) -> list[int | None]:
    """Map word tokens to word units, preferring the reading that matches the
    pack's context-aware reading. Unseen words get a unit so they can be mined
    (with create=False they map to None instead: import previews write nothing)."""
    pack = get_pack(language)
    keys = [pack.unit_key(t) if t.kind == WORD else None for t in tokens]
    words = {k[1] for k in keys if k}
    by_head: dict[str, list[Unit]] = {}
    if words:
        for u in db.scalars(
            select(Unit).where(Unit.language == language, Unit.type == "word", Unit.headword.in_(words)).order_by(Unit.id)
        ):
            by_head.setdefault(u.headword, []).append(u)

    out: list[int | None] = []
    for t, key in zip(tokens, keys):
        if key is None:
            out.append(None)
            continue
        _, head, reading = key
        cands = by_head.get(head, [])
        unit = next((u for u in cands if u.reading == reading), None)
        if unit is None:
            unit = next((u for u in cands if (u.extra or {}).get("primary_form")), None) or (cands[0] if cands else None)
        if unit is None and not create:
            out.append(None)
            continue
        if unit is None:
            unit = Unit(language=language, type="word", headword=head, reading=reading,
                        extra={"source": "segmenter"})
            db.add(unit)
            db.flush()
            by_head[head] = [unit]
        out.append(unit.id)
    return out


def create_text(db: Session, user_id: int, language: str, title: str, body: str,
                provenance: str = "imported", source_url: str | None = None) -> Text:
    tokens = get_pack(language).analyze(body)
    unit_ids = resolve_units(db, language, tokens)
    known = known_unit_ids(db, user_id, language)
    cov = coverage([u for t, u in zip(tokens, unit_ids) if t.kind == WORD], known, ignored_unit_ids(db, user_id))
    text = Text(user_id=user_id, language=language, title=title, body=body, provenance=provenance,
                source_url=source_url, coverage_at_creation=cov)
    text.tokens = [
        TextToken(position=i, sentence_index=t.sentence_index, surface=t.surface, kind=t.kind, unit_id=u)
        for i, (t, u) in enumerate(zip(tokens, unit_ids))
    ]
    db.add(text)
    db.commit()
    return text


def unit_statuses(db: Session, user_id: int, language: str, unit_ids: set[int]) -> dict[int, str]:
    known = known_unit_ids(db, user_id, language)
    ignored = ignored_unit_ids(db, user_id)
    carded = set(db.scalars(select(Card.unit_id).where(Card.user_id == user_id, Card.unit_id.in_(unit_ids))))
    out = {}
    for u in unit_ids:
        out[u] = IGNORED if u in ignored else KNOWN if u in known else LEARNING if u in carded else NEW
    return out


def token_dict(t: Token, unit_id: int | None, status: str | None) -> dict:
    """A token as the PWA renders it: reading aid per part, plus lemma and morphology
    for inflecting languages (bn: করছি -> lemma করা, morph -ছি)."""
    d = {"surface": t.surface, "kind": t.kind, "unit_id": unit_id, "status": status,
         "show_reading": t.kind == "proper" or status in (NEW, LEARNING),
         "syllables": [s.__dict__ for s in t.syllables]}
    if t.lemma:
        d["lemma"] = t.lemma
    if t.morph:
        d["morph"] = [m.__dict__ for m in t.morph]
    return d


def serialize_text(db: Session, user_id: int, text: Text) -> dict:
    """Tokens with status and reading aids. Pinyin is recomputed (cheap) rather
    than stored, so sandhi or reading fixes apply to old texts too."""
    analyzed = get_pack(text.language).analyze(text.body)
    surfaces_match = [a.surface for a in analyzed] == [t.surface for t in text.tokens]
    statuses = unit_statuses(db, user_id, text.language, {t.unit_id for t in text.tokens if t.unit_id})
    eligible = [t.unit_id for t in text.tokens if t.kind == WORD]
    known = {u for u, s in statuses.items() if s == KNOWN}
    ignored = {u for u, s in statuses.items() if s == IGNORED}
    tokens = []
    for i, tok in enumerate(text.tokens):
        status = statuses.get(tok.unit_id) if tok.unit_id else None
        a = analyzed[i] if surfaces_match else Token(surface=tok.surface, kind=tok.kind, sentence_index=tok.sentence_index)
        d = token_dict(a, tok.unit_id, status)
        d["show_reading"] = status in (NEW, LEARNING)
        tokens.append({"position": tok.position, "sentence_index": tok.sentence_index, **d})
    return {
        "id": text.id,
        "title": text.title,
        "language": text.language,
        "provenance": text.provenance,
        "source_url": text.source_url,
        "coverage_at_creation": text.coverage_at_creation,
        "coverage_now": coverage(eligible, known, ignored),
        "finished_at": text.finished_at,
        "meta": text.meta or {},
        "tokens": tokens,
    }


def sentence_map(sentences: list[str], language: str = "zh") -> list[int]:
    """For each reader sentence (the pack's splitter), the index of the source
    sentence it came from, so translations line up under the right text."""
    pack = get_pack(language)
    out: list[int] = []
    for i, sentence in enumerate(sentences):
        toks = pack.analyze(sentence)
        out += [i] * (max((t.sentence_index for t in toks), default=0) + 1)
    return out


def now() -> datetime:
    return datetime.now(timezone.utc)
