"""The PWA schedules offline with ts-fsrs (web/src/scheduler.ts); the server with
py-fsrs. They must agree on state, step, stability and difficulty, and on due
times for short (learning) intervals. Long intervals may differ by a day because
ts-fsrs never lets a review interval shrink; the server recomputes on sync.

Skipped when node or web/node_modules is missing (run `npm ci` in web/)."""

import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fsrs import Card, Rating, Scheduler

WEB = Path(__file__).resolve().parents[2] / "web"
DRIVER = WEB / "tests" / "fsrs_driver.ts"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not (WEB / "node_modules" / "ts-fsrs").exists(),
    reason="node and web/node_modules required",
)

CASES = [
    ([], [[3, 0], [3, 1], [3, 10], [1, 60 * 24 * 2], [3, 10], [3, 15]]),  # new card, all offline
    ([[3, 0], [3, 10]], [[1, 60 * 24 * 2], [3, 10], [3, 10]]),  # graduated online, lapses offline
    ([[3, 0], [1, 1], [3, 1]], [[3, 10], [4, 60 * 24]]),  # mid learning steps
    ([[4, 0], [3, 60 * 24 * 9]], [[2, 60 * 24 * 20], [1, 60 * 24 * 40], [3, 10]]),
]


def _state(c: Card) -> dict:
    return {"state": int(c.state), "step": c.step, "stability": c.stability, "difficulty": c.difficulty,
            "due": c.due.isoformat(), "last_review": c.last_review.isoformat() if c.last_review else None,
            "lapses": 0}


@pytest.mark.parametrize("pre,post", CASES)
def test_ts_fsrs_matches_py_fsrs(pre, post):
    s = Scheduler(enable_fuzzing=False)
    params = {"version": "FSRS-6", "weights": list(s.parameters), "desired_retention": s.desired_retention,
              "learning_steps_minutes": [t.total_seconds() / 60 for t in s.learning_steps],
              "relearning_steps_minutes": [t.total_seconds() / 60 for t in s.relearning_steps],
              "maximum_interval": s.maximum_interval}
    now = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
    card = Card(due=now)
    for g, m in pre:
        now += timedelta(minutes=m)
        card, _ = s.review_card(card, Rating(g), now)
    out = subprocess.run(["node", str(DRIVER), json.dumps(params), json.dumps(_state(card)), json.dumps(post)],
                         cwd=WEB, capture_output=True, text=True, check=True).stdout
    for (g, m), t in zip(post, json.loads(out)):
        now += timedelta(minutes=m)
        card, _ = s.review_card(card, Rating(g), now)
        assert (int(card.state), card.step) == (t["state"], t["step"])
        assert t["stability"] == pytest.approx(card.stability, rel=1e-6)
        assert t["difficulty"] == pytest.approx(card.difficulty, abs=1e-6)
        ts_due = datetime.fromisoformat(t["due"].replace("Z", "+00:00"))
        if card.due - now < timedelta(days=1):
            assert abs(ts_due - card.due) < timedelta(seconds=1)
        else:
            assert timedelta(0) <= ts_due - card.due <= timedelta(days=1)
