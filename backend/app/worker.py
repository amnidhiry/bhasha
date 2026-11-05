"""The background worker: `python -m app.worker`. Runs as its own container from
the same image as the API (see docker-compose.yml)."""

import logging
import signal
import time

from app.bootstrap import warm_packs
from app.db import SessionLocal
from app.fsrs_fit import maybe_schedule
from app.jobs import enqueue, requeue_stale, run_once

IDLE_SECONDS = 2.0
log = logging.getLogger("bhasha.worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True
        log.info("stopping after the current job")

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with SessionLocal() as db:
        warm_packs(db)  # same segmenter dictionary as the API
        if n := requeue_stale(db):
            log.info("requeued %d stale jobs", n)
    log.info("worker ready")
    last_sweep = 0.0  # sweep (stale jobs, nightly fits) right away
    while not stopping:
        job = run_once(SessionLocal)
        if job is not None:
            log.info("job %s %s: %s", job.id, job.kind, job.status)
            continue
        if time.monotonic() - last_sweep > 300:
            with SessionLocal() as db:
                requeue_stale(db)
                if n := maybe_schedule(db, enqueue):
                    log.info("queued %d nightly FSRS fits", n)
            last_sweep = time.monotonic()
        time.sleep(IDLE_SECONDS)


if __name__ == "__main__":
    main()
