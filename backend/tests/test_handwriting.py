import uuid
from datetime import datetime, timezone


def test_strokes_endpoint_serves_hanzi_writer_format(client):
    r = client.get("/api/hanzi/银")
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    d = r.json()
    assert len(d["strokes"]) == len(d["medians"]) == 11  # 银 has 11 strokes
    assert client.get("/api/hanzi/𠀀").status_code == 404


def test_overview_counts_official_bands(client):
    bands = {b["band"]: b for b in client.get("/api/handwriting").json()["bands"]}
    assert bands["1-2"]["total"] == 2 and bands["3"]["total"] == 2 and bands["4"]["total"] == 0


def test_add_from_list_follows_list_order_then_skips_existing(client):
    first = client.post("/api/handwriting/add", json={"from_list": 3}).json()["created"]
    assert [c["character"] for c in first] == ["爱", "我", "银"]
    more = client.post("/api/handwriting/add", json={"from_list": 3}).json()["created"]
    assert [c["character"] for c in more] == ["行"]


def test_add_specific_characters_from_a_word(client):
    created = client.post("/api/handwriting/add", json={"characters": ["银行", "ab"], "context": "银行"}).json()["created"]
    assert [c["character"] for c in created] == ["银", "行"]


def test_writing_and_words_are_separate_sessions(client):
    client.post("/api/handwriting/add", json={"characters": ["我"]})
    t = client.post("/api/texts/import", json={"title": "t", "body": "我在银行工作。"}).json()
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "s"})

    writing = client.get("/api/reviews/due", params={"mode": "writing"}).json()
    words = client.get("/api/reviews/due").json()
    assert [c["facet"] for c in writing] == ["handwriting"] and writing[0]["headword"] == "我"
    assert writing[0]["meanings"] and writing[0]["reading_display"] == "wǒ"
    assert all(c["facet"] != "handwriting" for c in words)

    # A handwriting review counts toward the writing caps only.
    client.post("/api/reviews", json=[{"id": str(uuid.uuid4()), "card_id": writing[0]["card_id"], "rating": 3,
                                       "reviewed_at": datetime.now(timezone.utc).isoformat(), "source": "handwriting"}])
    assert len(client.get("/api/reviews/due").json()) == 1


def test_new_handwriting_cap(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "max_new_handwriting_per_day", 2)
    client.post("/api/handwriting/add", json={"from_list": 4})
    assert len(client.get("/api/reviews/due", params={"mode": "writing"}).json()) == 2
