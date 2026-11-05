"""The learner model: FSRS state per card, plus knownness and coverage.

Reviews are the strong signal. Reading exposures are logged but never count as
a successful review. A word is known when its meaning card's recall probability
is at least `known_threshold`, or it is manually marked known."""

from collections.abc import Iterable
from datetime import datetime, timezone
from functools import lru_cache

from fsrs import Card as FsrsCard
from fsrs import Rating, Scheduler, State
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Card, ReviewLog, Unit, UnitMark

LEECH_LAPSES = 8


@lru_cache
def scheduler(desired_retention: float | None = None, fuzz: bool = True) -> Scheduler:
    # TODO(phase 1): load per-user parameters fitted by the nightly optimizer job.
    return Scheduler(
        desired_retention=desired_retention or get_settings().desired_retention,
        enable_fuzzing=fuzz,
    )


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def to_fsrs(card: Card) -> FsrsCard:
    return FsrsCard(
        card_id=card.id,
        state=State(card.state),
        step=card.step,
        stability=card.stability,
        difficulty=card.difficulty,
        due=_aware(card.due),
        last_review=_aware(card.last_review),
    )


def load_fsrs(card: Card, f: FsrsCard) -> None:
    card.state = int(f.state)
    card.step = f.step
    card.stability = f.stability
    card.difficulty = f.difficulty
    card.due = f.due
    card.last_review = f.last_review


def retrievability(card: Card, now: datetime | None = None) -> float:
    if card.last_review is None or card.stability is None:
        return 0.0
    return scheduler().get_card_retrievability(to_fsrs(card), now or datetime.now(timezone.utc))


def apply_review(card: Card, rating: int, reviewed_at: datetime, duration_ms: int | None = None) -> None:
    """Apply one review in chronological order."""
    was_review = card.state == int(State.Review)
    f, _ = scheduler().review_card(to_fsrs(card), Rating(rating), _aware(reviewed_at), duration_ms)
    load_fsrs(card, f)
    if rating == int(Rating.Again) and was_review:
        card.lapses += 1


def replay(card: Card, logs: Iterable[ReviewLog]) -> None:
    """Rebuild a card's state from its full history. Used when an offline client
    syncs a review older than the card's last review, so arrival order never matters.
    Fuzzing is off during replay so the result is deterministic."""
    sched = scheduler(fuzz=False)
    sim = FsrsCard(card_id=card.id, due=_aware(card.created_at))
    lapses = 0
    for log in sorted(logs, key=lambda l: _aware(l.reviewed_at)):
        if log.rating == int(Rating.Again) and sim.state == State.Review:
            lapses += 1
        sim, _ = sched.review_card(sim, Rating(log.rating), _aware(log.reviewed_at), log.duration_ms)
    load_fsrs(card, sim)
    card.lapses = lapses


def is_leech(card: Card) -> bool:
    return card.lapses >= LEECH_LAPSES


def known_unit_ids(db: Session, user_id: int, language: str, now: datetime | None = None) -> set[int]:
    # Personal scale (thousands of cards): computing R in Python is fine. Move to SQL
    # (R = (1 + factor * t / S) ** decay) if this ever gets slow.
    threshold = get_settings().known_threshold
    now = now or datetime.now(timezone.utc)
    known = set(
        db.scalars(
            select(UnitMark.unit_id)
            .join(Unit, Unit.id == UnitMark.unit_id)
            .where(UnitMark.user_id == user_id, UnitMark.status == "known", Unit.language == language)
        )
    )
    cards = db.scalars(
        select(Card).join(Unit).where(
            Card.user_id == user_id, Card.facet == "meaning", Unit.language == language
        )
    )
    # Only graduated cards count: a card in its first learning steps has R near 1.0
    # minutes after being seen, which says nothing about tomorrow.
    known.update(
        c.unit_id for c in cards if c.state == int(State.Review) and retrievability(c, now) >= threshold
    )
    return known


def ignored_unit_ids(db: Session, user_id: int) -> set[int]:
    return set(db.scalars(select(UnitMark.unit_id).where(UnitMark.user_id == user_id, UnitMark.status == "ignored")))


def coverage(unit_ids: Iterable[int | None], known: set[int], ignored: set[int] = frozenset()) -> float | None:
    """Share of coverage-eligible tokens that are known. Ignored units are excluded
    from the denominator, like proper nouns and numbers."""
    eligible = [u for u in unit_ids if u not in ignored]
    if not eligible:
        return None
    return sum(1 for u in eligible if u is not None and u in known) / len(eligible)
