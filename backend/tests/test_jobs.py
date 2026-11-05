from datetime import datetime, timedelta, timezone

import pytest

from app import jobs
from app.llm import gateway
from app.llm.providers import FakeProvider
from app.models import Job
from tests.test_generator import story


@pytest.fixture()
def fake(monkeypatch):
    f = FakeProvider()
    monkeypatch.setattr(gateway, "override", f)
    return f


def test_generate_job_runs_in_worker(client, fake):
    fake.replies = [story(("我在银行工作。", "I work at a bank."))]
    r = client.post("/api/jobs/generate", json={"topic": "work", "targets": ["银行"]})
    assert r.status_code == 202 and r.json()["status"] == "queued"
    jid = r.json()["id"]
    assert [j["id"] for j in client.get("/api/jobs").json()] == [jid]

    done = jobs.run_once(client.session_factory)
    assert done.status == "done"
    assert jobs.run_once(client.session_factory) is None  # queue empty

    j = client.get(f"/api/jobs/{jid}").json()
    assert j["status"] == "done" and j["result"]["title"] == "工作"
    assert client.get(f"/api/texts/{j['result']['text_id']}").json()["provenance"] == "generated"
    client.post(f"/api/jobs/{jid}/seen")
    assert client.get("/api/jobs").json() == []


def test_generate_without_model_fails_fast(client):
    r = client.post("/api/jobs/generate", json={"topic": "x"})
    assert r.status_code == 409 and "Sign in with ChatGPT" in r.json()["detail"]


def test_failed_job_keeps_message_and_can_retry(client, fake):
    from app.llm.errors import PlanLimitError

    def limited(_prompt):
        raise PlanLimitError()
    fake.replies = [limited]
    jid = client.post("/api/jobs/generate", json={"topic": "x"}).json()["id"]
    failed = jobs.run_once(client.session_factory)
    assert failed.status == "failed" and "usage limit" in failed.error
    retried = client.post(f"/api/jobs/{jid}/retry").json()
    assert retried["status"] == "queued" and retried["params"]["topic"] == "x"
    assert [j["id"] for j in client.get("/api/jobs").json()] == [retried["id"]]  # the old one is marked seen


def test_unexpected_error_is_logged_not_leaked(client, fake, monkeypatch):
    def boom(db, job):
        raise KeyError("secret detail")
    monkeypatch.setitem(jobs.HANDLERS, "generate", boom)
    client.post("/api/jobs/generate", json={"topic": "x"})
    failed = jobs.run_once(client.session_factory)
    assert failed.status == "failed" and "secret detail" not in failed.error and "KeyError" in failed.error


def test_stale_running_jobs_are_requeued_then_failed(client):
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    with client.session_factory() as s:
        s.add_all([Job(user_id=1, kind="generate", status="running", started_at=old, attempts=1),
                   Job(user_id=1, kind="generate", status="running", started_at=old, attempts=2)])
        s.commit()
        assert jobs.requeue_stale(s) == 1
        assert sorted(j.status for j in s.query(Job)) == ["failed", "queued"]


def test_inline_jobs_mode_runs_without_worker(client, fake, monkeypatch):
    from app.config import get_settings
    import app.db as dbmod
    monkeypatch.setattr(get_settings(), "inline_jobs", True)
    monkeypatch.setattr(dbmod, "SessionLocal", client.session_factory)
    fake.replies = [story(("我在银行工作。", "I work at a bank."))]
    jid = client.post("/api/jobs/generate", json={"topic": "work", "targets": ["银行"]}).json()["id"]
    assert client.get(f"/api/jobs/{jid}").json()["status"] == "done"


def test_two_workers_never_claim_the_same_job(client):
    """Postgres only: SKIP LOCKED hands concurrent workers different jobs."""
    with client.session_factory() as s:
        if s.get_bind().dialect.name != "postgresql":
            pytest.skip("needs Postgres (BHASHA_TEST_DATABASE_URL)")
        s.add_all([Job(user_id=1, kind="generate", status="queued") for _ in range(2)])
        s.commit()
    a, b = client.session_factory(), client.session_factory()
    try:
        # Hold a's row lock open (no commit yet) while b claims.
        from sqlalchemy import select
        locked = a.scalar(select(Job).where(Job.status == "queued").order_by(Job.id).limit(1)
                          .with_for_update(skip_locked=True))
        other = jobs.claim(b)
        assert locked is not None and other is not None and other.id != locked.id
    finally:
        a.rollback(); a.close(); b.close()
