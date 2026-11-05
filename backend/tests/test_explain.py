from app.llm import gateway
from app.llm.providers import FakeProvider


def test_explain_returns_answer_chunks_and_wiki_links(client, monkeypatch):
    fake = FakeProvider(replies=[{
        "answer": "了 shows the visit is finished.",
        "chunks": [{"zh": "我", "role": "subject: I"}, {"zh": "昨天", "role": "time: yesterday"},
                   {"zh": "去了", "role": "verb + 了: went"}, {"zh": "朋友家。", "role": "place: friend's home"}],
        "points": [{"name": "了 for completed actions", "search": "了 completed action"}]}])
    monkeypatch.setattr(gateway, "override", fake)
    r = client.post("/api/explain", json={"sentence": "我昨天去了朋友家。", "question": "Why 了 here?", "focus": "了"}).json()
    assert r["answer"].startswith("了") and len(r["chunks"]) == 4
    assert r["points"][0]["url"].startswith("https://resources.allsetlearning.com/") and "%E4%BA%86" in r["points"][0]["url"]
    assert "Why 了 here?" in fake.calls[0]["user"] and "Never write pinyin" in fake.calls[0]["system"]


def test_chunks_that_dont_rebuild_the_sentence_are_dropped(client, monkeypatch):
    monkeypatch.setattr(gateway, "override", FakeProvider(replies=[{
        "answer": "x", "chunks": [{"zh": "我们", "role": "?"}], "points": []}]))
    assert client.post("/api/explain", json={"sentence": "我昨天去了朋友家。"}).json()["chunks"] == []


def test_explain_needs_a_model(client):
    assert client.post("/api/explain", json={"sentence": "我好。"}).status_code == 409
