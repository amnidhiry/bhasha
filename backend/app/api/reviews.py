from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_language, current_user
from app.config import get_settings
from app.db import get_db
from app.learner import _aware, apply_review, is_leech, replay, retrievability, user_scheduler
from app.models import AppUser, Card, ReviewLog, Unit, UserFsrs
from app.packs import get_pack
from fsrs import State

router = APIRouter(prefix="/reviews", tags=["reviews"])


def day_start(now: datetime) -> datetime:
    tz = ZoneInfo(get_settings().timezone)
    local = now.astimezone(tz)
    return datetime.combine(local.date(), time(0), tz).astimezone(timezone.utc)


def meanings_for(db: Session, unit: Unit) -> list[str]:
    """Glosses for a card's unit, from its language pack (zh: HSK, then CC-CEDICT)."""
    return get_pack(unit.language).meanings(db, unit)


class FsrsState(BaseModel):
    """Card memory state, so offline clients can run the same FSRS-6 scheduler."""
    state: int  # 1 learning, 2 review, 3 relearning (py-fsrs has no separate "new")
    step: int | None
    stability: float | None
    difficulty: float | None
    due: datetime
    last_review: datetime | None
    lapses: int


class DueCard(BaseModel):
    card_id: int
    language: str = "zh"
    unit_id: int
    facet: str
    headword: str
    reading: str
    reading_display: str
    meanings: list[str]
    classifiers: list[str]
    context_sentence: str | None
    due: datetime
    is_new: bool
    leech: bool
    retrievability: float
    fsrs: FsrsState
    cloze: dict | None = None


class SchedulerParams(BaseModel):
    version: str
    weights: list[float]
    desired_retention: float
    retention_by_facet: dict[str, float] = {}
    learning_steps_minutes: list[float]
    relearning_steps_minutes: list[float]
    maximum_interval: int


@router.get("/params", response_model=SchedulerParams)
def params(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """The exact scheduler the server runs, mirrored by ts-fsrs in the PWA."""
    sch = user_scheduler(db, user.id)
    u = db.get(UserFsrs, user.id)
    return SchedulerParams(
        version="FSRS-6",
        weights=list(sch.parameters),
        desired_retention=sch.desired_retention,
        retention_by_facet={k: float(v) for k, v in ((u.retention_by_facet or {}) if u else {}).items()},
        learning_steps_minutes=[s.total_seconds() / 60 for s in sch.learning_steps],
        relearning_steps_minutes=[s.total_seconds() / 60 for s in sch.relearning_steps],
        maximum_interval=sch.maximum_interval,
    )


def backlog(db: Session, user_id: int, mode: str, now: datetime) -> int:
    """Reviewed cards that are due now (new cards don't count)."""
    in_mode = (Card.facet == "handwriting") if mode == "writing" else (Card.facet != "handwriting")
    return db.scalar(select(func.count()).select_from(Card).where(
        Card.user_id == user_id, ~Card.suspended, Card.due <= now, Card.last_review.is_not(None), in_mode)) or 0


def new_cards_paused(db: Session, user_id: int, mode: str, now: datetime) -> bool:
    """Reading first: when the backlog is high, clear it before adding new cards."""
    u = db.get(UserFsrs, user_id)
    enabled = u.reading_first if u else True
    threshold = u.backlog_threshold if u else 60
    return bool(enabled) and backlog(db, user_id, mode, now) > threshold


@router.get("/status")
def review_status(mode: str = "words", db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    now = datetime.now(timezone.utc)
    u = db.get(UserFsrs, user.id)
    return {"backlog": backlog(db, user.id, mode, now), "threshold": u.backlog_threshold if u else 60,
            "reading_first": u.reading_first if u else True, "new_paused": new_cards_paused(db, user.id, mode, now)}


@router.get("/due", response_model=list[DueCard])
def due(limit: int = 50, mode: str = "words", db: Session = Depends(get_db), user: AppUser = Depends(current_user),
        lang: str = Depends(current_language)):
    """Due cards for one session. mode=words: everything but handwriting;
    mode=writing: handwriting only. Each mode has its own daily caps, so a
    writing session never eats the reading-and-review budget. Only the active
    language's cards are served; the daily caps are shared across languages."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    today = day_start(now)
    in_mode = (Card.facet == "handwriting") if mode == "writing" else (Card.facet != "handwriting")
    max_reviews = s.max_handwriting_per_day if mode == "writing" else s.max_reviews_per_day
    max_new = s.max_new_handwriting_per_day if mode == "writing" else s.max_new_cards_per_day

    done_today = db.scalar(
        select(func.count()).select_from(ReviewLog).join(Card, Card.id == ReviewLog.card_id).where(
            ReviewLog.user_id == user.id, ReviewLog.scheduled, ReviewLog.reviewed_at >= today, in_mode)
    ) or 0
    first_reviews = (
        select(ReviewLog.card_id).join(Card, Card.id == ReviewLog.card_id).where(ReviewLog.user_id == user.id, in_mode)
        .group_by(ReviewLog.card_id).having(func.min(ReviewLog.reviewed_at) >= today)
    )
    new_today = db.scalar(select(func.count()).select_from(first_reviews.subquery())) or 0
    # Units reviewed today through any facet: siblings must wait until tomorrow.
    reviewed_units_today = {
        (unit_id, card_id) for unit_id, card_id in db.execute(
            select(Card.unit_id, Card.id).join(ReviewLog, ReviewLog.card_id == Card.id)
            .where(ReviewLog.user_id == user.id, ReviewLog.reviewed_at >= today)
        )
    }
    budget = max(0, min(limit, max_reviews - done_today))
    new_budget = max(0, max_new - new_today)
    if new_cards_paused(db, user.id, mode, now):
        new_budget = 0

    out: list[DueCard] = []
    seen_units: set[int] = set()
    sched = user_scheduler(db, user.id)
    cards = db.scalars(
        select(Card).join(Unit, Card.unit_id == Unit.id)
        .where(Card.user_id == user.id, ~Card.suspended, Card.due <= now, in_mode, Unit.language == lang)
        .order_by(Card.due)
    )
    for c in cards:
        if len(out) >= budget:
            break
        sibling_done = any(u == c.unit_id and cid != c.id for u, cid in reviewed_units_today)
        if c.unit_id in seen_units or sibling_done:
            continue
        is_new = c.last_review is None
        if is_new:
            if new_budget <= 0:
                continue
            new_budget -= 1
        seen_units.add(c.unit_id)
        out.append(DueCard(
            card_id=c.id, language=c.unit.language, unit_id=c.unit_id, facet=c.facet, headword=c.unit.headword,
            reading=c.unit.reading, reading_display=get_pack(c.unit.language).reading_display(c.unit.reading),
            meanings=meanings_for(db, c.unit), classifiers=(c.unit.extra or {}).get("classifiers", []),
            context_sentence=c.context_sentence, due=_aware(c.due), is_new=is_new, leech=is_leech(c),
            retrievability=retrievability(c, now, sched),
            cloze=c.cloze,
            fsrs=FsrsState(state=c.state, step=c.step, stability=c.stability, difficulty=c.difficulty,
                           due=_aware(c.due), last_review=_aware(c.last_review), lapses=c.lapses),
        ))
    return out


class ReviewIn(BaseModel):
    id: str = Field(min_length=8, max_length=64, description="client-generated UUID; makes sync idempotent")
    card_id: int
    rating: int = Field(ge=1, le=4)
    reviewed_at: datetime
    duration_ms: int | None = None
    source: str = "queue"
    scheduled: bool = True


class SyncResult(BaseModel):
    applied: list[str]
    duplicates: list[str]
    replayed_cards: list[int]


def add_listening_card_if_ready(db: Session, card: Card) -> None:
    """Listening cards switch on once the meaning card reaches review state."""
    if card.facet != "meaning" or card.state != int(State.Review):
        return
    exists = db.scalar(select(Card.id).where(
        Card.user_id == card.user_id, Card.unit_id == card.unit_id, Card.facet == "listening"))
    if exists is None:
        db.add(Card(user_id=card.user_id, unit_id=card.unit_id, facet="listening",
                    context_sentence=card.context_sentence, source_text_id=card.source_text_id,
                    due=datetime.now(timezone.utc) + timedelta(days=1)))


def record_reviews(db: Session, user_id: int, reviews: list[ReviewIn]) -> SyncResult:
    result = SyncResult(applied=[], duplicates=[], replayed_cards=[])
    scheds: dict[str, object] = {}

    def sched_for(card: Card):
        kind = card.facet.split(":", 1)[0]
        if kind not in scheds:
            scheds[kind] = user_scheduler(db, user_id, facet=card.facet)
        return scheds[kind]
    needs_replay: set[int] = set()
    for r in sorted(reviews, key=lambda r: _aware(r.reviewed_at)):
        if db.get(ReviewLog, r.id) is not None:
            result.duplicates.append(r.id)
            continue
        card = db.get(Card, r.card_id)
        if card is None or card.user_id != user_id:
            raise HTTPException(404, f"card {r.card_id} not found")
        db.add(ReviewLog(id=r.id, user_id=user_id, card_id=card.id, rating=r.rating,
                         reviewed_at=r.reviewed_at, duration_ms=r.duration_ms,
                         source=r.source, scheduled=r.scheduled))
        if card.id in needs_replay:
            pass
        elif card.last_review is not None and _aware(r.reviewed_at) < _aware(card.last_review):
            needs_replay.add(card.id)  # out-of-order offline sync
        else:
            apply_review(card, r.rating, r.reviewed_at, r.duration_ms, sched_for(card))
        result.applied.append(r.id)
    db.flush()
    for card_id in needs_replay:
        card = db.get(Card, card_id)
        replay(card, db.scalars(select(ReviewLog).where(ReviewLog.card_id == card_id)),
               user_scheduler(db, user_id, fuzz=False, facet=card.facet))
        result.replayed_cards.append(card_id)
    for card_id in {r.card_id for r in reviews}:
        add_listening_card_if_ready(db, db.get(Card, card_id))
    db.commit()
    return result


@router.post("", response_model=SyncResult)
def sync(reviews: list[ReviewIn], db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    return record_reviews(db, user.id, reviews)
