import uuid
from datetime import datetime, timedelta, timezone

from app.models import Card, Unit


def _cards(client, n, facet="meaning", reviewed=False):
    """n cards on fresh units; reviewed ones are due now with a review history."""
    now = datetime.now(timezone.utc)
    ids = []
    with client.session_factory() as s:
        for i in range(n):
            u = Unit(language="zh", type="word", headword=f"词{facet}{i}{reviewed}", reading="ci2")
            s.add(u)
            s.flush()
            c = Card(user_id=1, unit_id=u.id, facet=facet, due=now - timedelta(hours=1))
            if reviewed:
                c.state, c.stability, c.difficulty = 2, 3.0, 5.0
                c.last_review = now - timedelta(days=3)
            s.add(c)
            s.flush()
            ids.append(c.id)
        s.commit()
    return ids


def test_retention_per_card_type(client):
    r = client.put("/api/fsrs/retention", json={"desired_retention": 0.8, "facet": "listening"}).json()
    assert r["retention_by_facet"] == {"listening": 0.8}
    assert client.get("/api/reviews/params").json()["retention_by_facet"] == {"listening": 0.8}
    meaning = _cards(client, 1, "meaning", reviewed=True)[0]
    listening = _cards(client, 1, "listening", reviewed=True)[0]
    now = datetime.now(timezone.utc).isoformat()
    client.post("/api/reviews", json=[{"id": str(uuid.uuid4()), "card_id": cid, "rating": 3, "reviewed_at": now}
                                      for cid in (meaning, listening)])
    with client.session_factory() as s:
        m, l = s.get(Card, meaning), s.get(Card, listening)
        assert l.due > m.due  # a lower recall target means a longer interval for the same memory
    # Clearing the per-type value returns it to the default.
    assert client.put("/api/fsrs/retention", json={"desired_retention": None, "facet": "listening"}).json()[
        "retention_by_facet"] == {}


def test_reading_first_pauses_new_cards_when_backlog_is_high(client):
    _cards(client, 3, reviewed=False)  # new
    _cards(client, 12, reviewed=True)  # backlog
    client.put("/api/fsrs/reading-first", json={"enabled": True, "threshold": 10})
    st = client.get("/api/reviews/status").json()
    assert st["backlog"] == 12 and st["new_paused"]
    due = client.get("/api/reviews/due").json()
    assert due and not any(c["is_new"] for c in due)
    client.put("/api/fsrs/reading-first", json={"enabled": False, "threshold": 10})
    assert any(c["is_new"] for c in client.get("/api/reviews/due").json())
    assert client.put("/api/fsrs/reading-first", json={"enabled": True, "threshold": 5}).status_code == 422
