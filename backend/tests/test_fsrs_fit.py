"""The nightly re-fit on a simulated learner whose memory differs from FSRS's
default model. Needs PyTorch (the worker image has it); skipped otherwise."""

import random
from datetime import datetime, timedelta, timezone

import pytest

torch = pytest.importorskip("torch")

from fsrs import Card as FsrsCard  # noqa: E402
from fsrs import Rating, Scheduler  # noqa: E402

from app import fsrs_fit  # noqa: E402
from app.models import Card, ReviewLog, Unit, UserFsrs  # noqa: E402

DEFAULT = list(Scheduler().parameters)
# This learner keeps new words four times longer, and stability grows faster with
# each success. With ~4,700 reviews that difference is detectable; with ~2,400 and
# a smaller difference the held-out check (rightly) rejects the fit as overfitting.
TRUE = [*(w * 4 for w in DEFAULT[0:4]), *DEFAULT[4:8], DEFAULT[8] + 0.6, *DEFAULT[9:]]


def simulate(n_cards=600, days=200, seed=3):
    """Cards scheduled by the default scheduler; recall drawn from the TRUE model."""
    rng = random.Random(seed)
    app_s = Scheduler(enable_fuzzing=False)
    true_s = Scheduler(parameters=TRUE, enable_fuzzing=False)
    start = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    cards = []  # (card_id, app_card, true_card)
    logs = []
    for day in range(days):
        now_day = start + timedelta(days=day)
        if day < 60:
            for _ in range(n_cards // 60):
                cid = len(cards) + 1
                cards.append([cid, FsrsCard(card_id=cid, due=now_day), FsrsCard(card_id=cid, due=now_day)])
        end = now_day + timedelta(hours=12)
        while True:
            due = [c for c in cards if c[1].due <= end]
            if not due:
                break
            c = min(due, key=lambda c: c[1].due)
            at = max(c[1].due, now_day)
            p = true_s.get_card_retrievability(c[2], at) if c[2].last_review else 0.0
            if c[2].last_review is None:
                recalled = rng.random() < 0.7  # first sight: guess from context
            else:
                recalled = rng.random() < p
            rating = Rating.Again if not recalled else rng.choices([Rating.Hard, Rating.Good, Rating.Easy], [1, 8, 1])[0]
            c[1], _ = app_s.review_card(c[1], rating, at)
            c[2], _ = true_s.review_card(c[2], rating, at)
            logs.append((c[0], int(rating), at, rng.randint(2000, 9000)))
    return logs


@pytest.fixture(scope="module")
def sim_logs():
    return simulate()


def _load(client, logs):
    with client.session_factory() as s:
        unit = Unit(language="zh", type="word", headword="模拟", reading="mo2 ni3")
        s.add(unit)
        s.flush()
        ids = {}
        for cid in sorted({l[0] for l in logs}):
            card = Card(user_id=1, unit_id=unit.id, facet=f"sim{cid}", state=2)
            s.add(card)
            s.flush()
            ids[cid] = card.id
        s.bulk_insert_mappings(ReviewLog, [
            {"id": f"sim-{i}", "user_id": 1, "card_id": ids[cid], "rating": r, "reviewed_at": at, "duration_ms": ms,
             "source": "queue", "scheduled": True} for i, (cid, r, at, ms) in enumerate(logs)])
        s.commit()


def test_too_few_reviews_is_skipped(client):
    with client.session_factory() as s:
        f = fsrs_fit.fit(s, 1)
    assert f.status == "skipped" and "fitting starts at" in f.message
    assert client.post("/api/fsrs/fit").status_code == 409


def test_fit_recovers_a_better_model(client, sim_logs):
    assert len(sim_logs) > 4000
    _load(client, sim_logs)
    with client.session_factory() as s:
        result = fsrs_fit.fit(s, 1)
        u = s.get(UserFsrs, 1)
    assert result.status == "accepted", result.message
    m = result.metrics
    assert m["holdout_fitted"]["log_loss"] < m["holdout_current"]["log_loss"]
    assert m["holdout_fitted"]["n"] >= fsrs_fit.MIN_HOLDOUT
    assert m["holdout_fitted"]["rmse_bins"] < m["holdout_current"]["rmse_bins"]
    # The fit moves the initial stabilities toward this learner's longer memory.
    assert sum(u.weights[0:4]) > sum(DEFAULT[0:4])
    assert result.optimal_retention is None or 0.7 <= result.optimal_retention <= 0.95

    # The server and the PWA's offline scheduler switch to the fitted parameters.
    params = client.get("/api/reviews/params").json()
    assert params["weights"] == pytest.approx(u.weights)
    st = client.get("/api/fsrs").json()
    assert st["personalized"] and st["history"][0]["status"] == "accepted"

    # Not due again right away.
    with client.session_factory() as s:
        again = fsrs_fit.fit(s, 1)
    assert again.status == "skipped" and "Not due" in again.message


def test_retention_choice(client):
    st = client.put("/api/fsrs/retention", json={"desired_retention": 0.85}).json()
    assert st["desired_retention"] == 0.85 and not st["retention_is_default"]
    assert client.get("/api/reviews/params").json()["desired_retention"] == 0.85
    assert client.put("/api/fsrs/retention", json={"desired_retention": 0.5}).status_code == 422
    assert client.put("/api/fsrs/retention", json={"desired_retention": None}).json()["retention_is_default"]


def test_nightly_scheduling_queues_once(client, sim_logs, monkeypatch):
    _load(client, sim_logs)
    from app import jobs
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "timezone", "Etc/GMT+12")  # any hour works if we pin the clock below
    import app.fsrs_fit as ff

    class Late(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 5, 4, 0, tzinfo=tz) if tz else datetime(2026, 11, 5, 4, 0)
    monkeypatch.setattr(ff, "datetime", Late)
    with client.session_factory() as s:
        assert ff.maybe_schedule(s, jobs.enqueue) == 1
        assert ff.maybe_schedule(s, jobs.enqueue) == 0  # a fit job is already pending


def test_worse_fit_is_rejected(client, sim_logs, monkeypatch):
    """The held-out gate: parameters that predict held-out reviews worse are refused
    and the scheduler stays as it was."""
    import fsrs

    class BadOptimizer:
        def __init__(self, logs):
            pass

        def compute_optimal_parameters(self):
            return [*(w / 10 for w in DEFAULT[0:4]), *DEFAULT[4:]]  # forgets ten times faster

    monkeypatch.setattr(fsrs, "Optimizer", BadOptimizer)
    _load(client, sim_logs)
    with client.session_factory() as s:
        result = fsrs_fit.fit(s, 1)
        assert s.get(UserFsrs, 1) is None  # scheduler unchanged
    assert result.status == "rejected"
    assert result.metrics["holdout_fitted"]["log_loss"] > result.metrics["holdout_current"]["log_loss"]
