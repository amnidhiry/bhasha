"""Fit FSRS-6 parameters to the learner's own review log (the nightly re-fit).

1. Wait until there are enough reviews (MIN_REVIEWS), then re-fit monthly or
   when the log has grown by a quarter.
2. Split cards 80/20 by id. Fit on 80% with py-fsrs's Optimizer; score the
   current and the fitted parameters on the held-out 20% with log loss and
   binned RMSE (srs-benchmark's metrics).
3. Accept only if the fitted parameters predict the held-out reviews better;
   then re-fit on everything and switch the learner's scheduler to them.
4. Suggest an optimal retention (py-fsrs needs 512+ reviews with durations).
   It is shown, not applied: retention changes the daily workload.

The optimizer needs PyTorch, which is only installed in the worker image.
"""

import hashlib
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fsrs import Card as FsrsCard
from fsrs import Rating, ReviewLog as FsrsLog, Scheduler
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.learner import _aware
from app.models import FsrsFit, ReviewLog, UserFsrs

MIN_REVIEWS = 400
REFIT_DAYS = 30
REFIT_GROWTH = 1.25
HOLDOUT_SHARE = 5  # 1 in 5 cards
MIN_HOLDOUT = 50   # evaluable held-out reviews needed to judge a fit
DAY = 86400.0


def _holdout(card_id: int) -> bool:
    return int(hashlib.sha256(str(card_id).encode()).hexdigest(), 16) % HOLDOUT_SHARE == 0


def review_logs(db: Session, user_id: int) -> list[FsrsLog]:
    rows = db.execute(select(ReviewLog.card_id, ReviewLog.rating, ReviewLog.reviewed_at, ReviewLog.duration_ms)
                      .where(ReviewLog.user_id == user_id))
    return [FsrsLog(card_id=c, rating=Rating(r), review_datetime=_aware(at), review_duration=d) for c, r, at, d in rows]


def evaluate(weights: list[float] | tuple[float, ...] | None, logs: list[FsrsLog]) -> dict:
    """Predicted recall vs actual recall for every review at least a day after
    the previous one (long-term memory, as srs-benchmark scores it)."""
    sched = Scheduler(parameters=tuple(weights), enable_fuzzing=False) if weights else Scheduler(enable_fuzzing=False)
    by_card: dict[int, list[FsrsLog]] = defaultdict(list)
    for log in logs:
        by_card[log.card_id].append(log)
    preds: list[tuple[float, int]] = []
    for card_id, history in by_card.items():
        history.sort(key=lambda l: l.review_datetime)
        card = FsrsCard(card_id=card_id, due=history[0].review_datetime)
        for log in history:
            if card.last_review is not None and card.stability is not None \
                    and (log.review_datetime - card.last_review).total_seconds() >= DAY:
                p = sched.get_card_retrievability(card, log.review_datetime)
                preds.append((min(max(p, 1e-4), 1 - 1e-4), 0 if log.rating == Rating.Again else 1))
            card, _ = sched.review_card(card, log.rating, log.review_datetime)
    if not preds:
        return {"n": 0, "log_loss": None, "rmse_bins": None}
    log_loss = -sum(y * math.log(p) + (1 - y) * math.log(1 - p) for p, y in preds) / len(preds)
    bins: dict[int, list[tuple[float, int]]] = defaultdict(list)
    for p, y in preds:
        bins[min(9, int(p * 10))].append((p, y))
    mse = sum(len(b) * (sum(p for p, _ in b) / len(b) - sum(y for _, y in b) / len(b)) ** 2 for b in bins.values())
    return {"n": len(preds), "log_loss": round(log_loss, 5), "rmse_bins": round(math.sqrt(mse / len(preds)), 5)}


def _record(db: Session, user_id: int, status: str, message: str, n: int, **kw) -> FsrsFit:
    fit = FsrsFit(user_id=user_id, status=status, message=message, n_reviews=n, **kw)
    db.add(fit)
    db.commit()
    return fit


def due_reason(db: Session, user_id: int, n: int) -> str | None:
    """Why a fit should run now, or None."""
    if n < MIN_REVIEWS:
        return None
    current = db.get(UserFsrs, user_id)
    if current is None or current.fitted_at is None:
        return "first fit"
    if _aware(current.fitted_at) < datetime.now(timezone.utc) - timedelta(days=REFIT_DAYS):
        return "monthly re-fit"
    if n >= current.n_reviews * REFIT_GROWTH:
        return "review log grew by a quarter"
    return None


def fit(db: Session, user_id: int, force: bool = False) -> FsrsFit:
    logs = review_logs(db, user_id)
    n = len(logs)
    if n < MIN_REVIEWS:
        return _record(db, user_id, "skipped", f"{n} reviews so far; fitting starts at {MIN_REVIEWS}.", n)
    reason = due_reason(db, user_id, n)
    if reason is None and not force:
        return _record(db, user_id, "skipped", "Not due: fitted recently and the log hasn't grown enough.", n)

    from fsrs import Optimizer  # needs PyTorch (worker image)

    train = [l for l in logs if not _holdout(l.card_id)]
    held = [l for l in logs if _holdout(l.card_id)]
    current = db.get(UserFsrs, user_id)
    current_w = current.weights if current and current.weights else None
    trial = Optimizer(train).compute_optimal_parameters()
    before, after = evaluate(current_w, held), evaluate(trial, held)
    metrics = {"holdout_current": before, "holdout_fitted": after, "reason": reason or "manual"}
    if after["n"] < MIN_HOLDOUT:
        return _record(db, user_id, "skipped",
                       f"Only {after['n']} held-out reviews a day or more apart; need {MIN_HOLDOUT} to judge a fit.",
                       n, metrics=metrics)
    if after["log_loss"] >= before["log_loss"]:
        return _record(db, user_id, "rejected",
                       "The fitted parameters didn't predict held-out reviews better; keeping the current ones.",
                       n, weights=list(trial), metrics=metrics)

    final = list(Optimizer(logs).compute_optimal_parameters())
    metrics["all_current"], metrics["all_fitted"] = evaluate(current_w, logs), evaluate(final, logs)
    optimal = None
    timed = [l for l in logs if l.review_duration]
    if len(timed) >= 512:
        try:
            optimal = float(Optimizer(timed).compute_optimal_retention(final))
        except ValueError:
            optimal = None
    if current is None:
        current = UserFsrs(user_id=user_id, version=0)
        db.add(current)
    current.weights = final
    current.fitted_at = datetime.now(timezone.utc)
    current.n_reviews = n
    current.version = (current.version or 0) + 1
    gain = (before["log_loss"] - after["log_loss"]) / before["log_loss"] * 100
    return _record(db, user_id, "accepted",
                   f"New parameters predict held-out reviews {gain:.1f}% better (log loss).",
                   n, weights=final, metrics=metrics, optimal_retention=optimal)


def maybe_schedule(db: Session, enqueue) -> int:
    """Nightly: queue a fit for each learner once a day after 03:00 local time,
    when one is due. Returns how many were queued."""
    from zoneinfo import ZoneInfo

    from app.models import AppUser, Job

    local = datetime.now(ZoneInfo(get_settings().timezone))
    if local.hour < 3:
        return 0
    since = datetime.now(timezone.utc) - timedelta(hours=20)
    queued = 0
    for (user_id,) in db.execute(select(AppUser.id)):
        recent = db.scalar(select(FsrsFit.id).where(FsrsFit.user_id == user_id, FsrsFit.created_at >= since).limit(1))
        pending = db.scalar(select(Job.id).where(Job.user_id == user_id, Job.kind == "fsrs_fit",
                                                 Job.status.in_(("queued", "running"))).limit(1))
        if recent or pending:
            continue
        n = db.scalar(select(func.count()).select_from(ReviewLog).where(ReviewLog.user_id == user_id)) or 0
        if due_reason(db, user_id, n):
            enqueue(db, user_id, "fsrs_fit", {"force": False})
            queued += 1
    return queued
