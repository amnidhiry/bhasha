from datetime import datetime, timedelta, timezone

from app.learner import apply_review, coverage, replay, retrievability
from app.models import Card, ReviewLog

T0 = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)


def _card():
    return Card(id=1, user_id=1, unit_id=1, facet="meaning", state=1, step=0, due=T0, lapses=0, created_at=T0)


def test_new_card_has_zero_retrievability():
    assert retrievability(_card(), T0) == 0.0


def test_reviews_raise_stability():
    c = _card()
    apply_review(c, 3, T0)
    apply_review(c, 3, T0 + timedelta(minutes=10))
    assert c.state == 2 and c.stability > 0
    assert retrievability(c, T0 + timedelta(minutes=11)) > 0.9


def test_replay_is_order_independent():
    logs = [ReviewLog(id=str(i), card_id=1, rating=r, reviewed_at=T0 + timedelta(days=d))
            for i, (r, d) in enumerate([(3, 0), (3, 0.01), (1, 5), (3, 5.01)])]
    a, b = _card(), _card()
    replay(a, logs)
    replay(b, list(reversed(logs)))
    assert (a.stability, a.difficulty, a.due, a.state) == (b.stability, b.difficulty, b.due, b.state)
    assert a.lapses == 1


def test_coverage():
    assert coverage([1, 2, 3, None], {1, 2, 3}) == 0.75
    assert coverage([1, 2, 9], {1, 2}, ignored={9}) == 1.0
    assert coverage([], set()) is None
