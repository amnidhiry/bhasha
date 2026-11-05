from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import jobs as queue
from app.api.deps import current_user
from app.api.texts import GenerateIn
from app.config import get_settings
from app.llm import gateway
from app.llm.errors import NoModelError, SignInRequiredError
from app.db import get_db
from app.models import AppUser, Job

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobOut(BaseModel):
    id: int
    kind: str
    status: str
    params: dict
    result: dict
    error: str | None
    created_at: datetime
    finished_at: datetime | None

    model_config = {"from_attributes": True}


def _own(db: Session, user: AppUser, job_id: int) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(404, "job not found")
    return job


def _require_model(db: Session) -> None:
    """Fail now, not in the worker, when no model is connected."""
    try:
        gateway.provider_for(db)
    except (NoModelError, SignInRequiredError) as e:
        raise HTTPException(409, str(e))


def _run_inline():
    # Dev setups without a worker container (BHASHA_INLINE_JOBS=true).
    import app.db as dbmod
    queue.run_once(dbmod.SessionLocal)


@router.post("/generate", response_model=JobOut, status_code=202)
def generate(body: GenerateIn, tasks: BackgroundTasks, db: Session = Depends(get_db),
             user: AppUser = Depends(current_user)):
    """Queue a generated text. Poll GET /jobs/{id}; the result holds text_id."""
    _require_model(db)
    job = queue.enqueue(db, user.id, "generate", body.model_dump())
    if get_settings().inline_jobs:
        tasks.add_task(_run_inline)
    return job


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Jobs the user should hear about: still running, or finished and not yet seen."""
    rows = db.scalars(select(Job).where(Job.user_id == user.id, ~Job.seen).order_by(Job.created_at.desc()).limit(20))
    return list(rows)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    return _own(db, user, job_id)


@router.post("/{job_id}/seen", response_model=JobOut)
def mark_seen(job_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    job = _own(db, user, job_id)
    if job.status in ("done", "failed"):
        job.seen = True
        db.commit()
    return job


@router.post("/{job_id}/retry", response_model=JobOut, status_code=202)
def retry(job_id: int, tasks: BackgroundTasks, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    old = _own(db, user, job_id)
    if old.status != "failed":
        raise HTTPException(409, "only failed jobs can be retried")
    _require_model(db)
    old.seen = True
    job = queue.enqueue(db, user.id, old.kind, old.params)
    if get_settings().inline_jobs:
        tasks.add_task(_run_inline)
    return job
