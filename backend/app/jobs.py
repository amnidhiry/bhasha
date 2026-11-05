"""A small job queue in Postgres. The volume is a few jobs a day, so a table
plus SELECT ... FOR UPDATE SKIP LOCKED replaces Redis: one service fewer, and
queued work survives restarts. SQLite (dev) has no SKIP LOCKED; it runs one
worker, so a plain select is safe there."""

import logging
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.llm.errors import LlmError
from app.models import Job

log = logging.getLogger("bhasha.jobs")

# A running job whose worker died is requeued after this long.
STALE_AFTER = timedelta(minutes=15)
MAX_ATTEMPTS = 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(db: Session, user_id: int, kind: str, params: dict) -> Job:
    if kind not in HANDLERS:
        raise ValueError(f"unknown job kind {kind!r}")
    job = Job(user_id=user_id, kind=kind, params=params, status="queued")
    db.add(job)
    db.commit()
    return job


def requeue_stale(db: Session) -> int:
    cutoff = _now() - STALE_AFTER
    n = db.execute(
        update(Job).where(Job.status == "running", Job.started_at < cutoff, Job.attempts < MAX_ATTEMPTS)
        .values(status="queued")
    ).rowcount
    db.execute(
        update(Job).where(Job.status == "running", Job.started_at < cutoff, Job.attempts >= MAX_ATTEMPTS)
        .values(status="failed", error="The worker stopped while running this job.", finished_at=_now())
    )
    db.commit()
    return n or 0


def claim(db: Session) -> Job | None:
    q = select(Job).where(Job.status == "queued").order_by(Job.created_at, Job.id).limit(1)
    if db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    job = db.scalar(q)
    if job is None:
        db.rollback()
        return None
    job.status = "running"
    job.started_at = _now()
    job.attempts += 1
    db.commit()
    return job


def _generate(db: Session, job: Job) -> dict:
    from app.generator import generate

    p = job.params
    text = generate(db, job.user_id, p.get("topic", ""), p.get("genre", "story"), p.get("length", "medium"),
                    p.get("targets") or [])
    return {"text_id": text.id, "title": text.title}


HANDLERS: dict[str, Callable[[Session, Job], dict]] = {"generate": _generate}


def run(db: Session, job: Job) -> Job:
    try:
        result = HANDLERS[job.kind](db, job)
    except LlmError as e:  # expected failures: show the message as-is
        db.rollback()
        job = db.get(Job, job.id)
        job.status, job.error = "failed", str(e)
    except Exception as e:  # bugs: keep the trace in the log, a short message for the user
        db.rollback()
        log.error("job %s failed\n%s", job.id, traceback.format_exc())
        job = db.get(Job, job.id)
        job.status, job.error = "failed", f"Something went wrong ({type(e).__name__}). See the worker log."
    else:
        job.status, job.result = "done", result
    job.finished_at = _now()
    db.commit()
    return job


def run_once(session_factory) -> Job | None:
    """Claim and run one job. Returns it, or None when the queue is empty."""
    with session_factory() as db:
        job = claim(db)
        return run(db, job) if job else None
