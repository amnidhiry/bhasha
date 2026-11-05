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
    enqueue_render(db, job.user_id, text.id)
    return {"text_id": text.id, "title": text.title}


def _fsrs_fit(db: Session, job: Job) -> dict:
    from app.fsrs_fit import fit

    result = fit(db, job.user_id, force=bool(job.params.get("force")))
    return {"fit_id": result.id, "status": result.status, "message": result.message}


def _render_text(db: Session, job: Job) -> dict:
    """Pre-render a text's sentences so the reader's audio is instant."""
    from app.models import Text
    from app.packs import get_pack
    from app.speech import SpeechUnavailable, get_clip, hosts

    text = db.get(Text, job.params["text_id"])
    if text is None or not hosts():
        return {"rendered": 0}
    sentences: dict[int, str] = {}
    for t in get_pack(text.language).analyze(text.body):
        sentences[t.sentence_index] = sentences.get(t.sentence_index, "") + t.surface
    rendered = 0
    for s in sentences.values():
        s = s.strip()
        if not s:
            continue
        try:
            get_clip(db, s, RENDER_SPEED)
            rendered += 1
        except SpeechUnavailable as e:
            raise LlmError(f"Audio not rendered: {e}") from e  # shown as the job's message
    return {"rendered": rendered}


def _tone_check(db: Session, job: Job) -> dict:
    from app.speech import active, put_setting, setting
    from app.tonecheck import check_voice

    host = active()
    if host is None:
        raise LlmError("No speech host is reachable for the tone check.")
    voices = job.params.get("voices") or host[1].get("voices", [])[:8]
    results = setting(db, "tone_check")
    for v in voices:
        results[v] = {**check_voice(db, v), "engine": host[1].get("engine"), "device": host[1].get("device")}
        put_setting(db, "tone_check", results)
    return {"voices": len(voices)}


RENDER_SPEED = 0.85  # the speed the PWA asks for when playing sentences and words


def enqueue_render(db: Session, user_id: int, text_id: int) -> None:
    from app.speech import hosts

    if hosts():
        enqueue(db, user_id, "render_text", {"text_id": text_id})


HANDLERS: dict[str, Callable[[Session, Job], dict]] = {
    "generate": _generate, "fsrs_fit": _fsrs_fit, "render_text": _render_text, "tone_check": _tone_check,
}


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
