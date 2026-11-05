from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import jobs as queue
from app.api.deps import current_user
from app.config import get_settings
from app.db import get_db
from app.fsrs_fit import MIN_REVIEWS, due_reason
from app.models import AppUser, FsrsFit, Job, ReviewLog, UserFsrs

router = APIRouter(prefix="/fsrs", tags=["fsrs"])


def _status(db: Session, user_id: int) -> dict:
    u = db.get(UserFsrs, user_id)
    n = db.scalar(select(func.count()).select_from(ReviewLog).where(ReviewLog.user_id == user_id)) or 0
    fits = list(db.scalars(select(FsrsFit).where(FsrsFit.user_id == user_id).order_by(FsrsFit.id.desc()).limit(10)))
    suggestion = next((f.optimal_retention for f in fits if f.status == "accepted" and f.optimal_retention), None)
    running = db.scalar(select(Job.id).where(Job.user_id == user_id, Job.kind == "fsrs_fit",
                                             Job.status.in_(("queued", "running"))).limit(1))
    return {
        "personalized": bool(u and u.weights),
        "fitted_at": u.fitted_at if u else None,
        "desired_retention": (u.desired_retention if u and u.desired_retention else get_settings().desired_retention),
        "retention_is_default": not (u and u.desired_retention),
        "suggested_retention": suggestion,
        "reviews": n,
        "min_reviews": MIN_REVIEWS,
        "fit_due": due_reason(db, user_id, n),
        "fit_running": running is not None,
        "history": [{"id": f.id, "status": f.status, "message": f.message, "n_reviews": f.n_reviews,
                     "metrics": f.metrics, "optimal_retention": f.optimal_retention, "created_at": f.created_at}
                    for f in fits],
    }


@router.get("")
def status(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Whether scheduling is fitted to you yet, and every fit attempt with its metrics."""
    return _status(db, user.id)


@router.post("/fit", status_code=202)
def fit_now(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Queue a fit now (the worker also does this nightly when one is due)."""
    n = db.scalar(select(func.count()).select_from(ReviewLog).where(ReviewLog.user_id == user.id)) or 0
    if n < MIN_REVIEWS:
        raise HTTPException(409, f"{n} reviews so far; fitting needs {MIN_REVIEWS}.")
    queue.enqueue(db, user.id, "fsrs_fit", {"force": True})
    return _status(db, user.id)


class RetentionIn(BaseModel):
    desired_retention: float | None = Field(default=None, ge=0.7, le=0.97)


@router.put("/retention")
def set_retention(body: RetentionIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Target recall probability at review time. Higher means more reviews; null
    returns to the default. Applies to cards from their next review on."""
    u = db.get(UserFsrs, user.id)
    if u is None:
        u = UserFsrs(user_id=user.id, version=0)
        db.add(u)
    u.desired_retention = body.desired_retention
    u.version = (u.version or 0) + 1
    db.commit()
    return _status(db, user.id)
