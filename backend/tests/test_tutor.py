import pytest

from app.llm import gateway
from app.llm.providers import FakeProvider

NO_LEARNER = {"original": "", "corrected": "", "english": "", "errors": []}


def turn(reply_zh, reply_en="", learner=None, goal=False, hint="Say what you'd like to drink."):
    return {"learner": learner or NO_LEARNER, "reply": {"zh": reply_zh, "en": reply_en}, "goal_met": goal, "hint": hint}


@pytest.fixture()
def fake(monkeypatch):
    f = FakeProvider()
    monkeypatch.setattr(gateway, "override", f)
    return f


def test_scenarios_listed(client):
    s = client.get("/api/tutor/scenarios").json()
    assert {"restaurant", "doctor", "free"} <= {x["id"] for x in s}
    assert all(x["goal"] and x["completed"] == 0 for x in s)


def test_start_needs_a_model(client):
    assert client.post("/api/tutor/sessions", json={"scenario": "restaurant"}).status_code == 409


def test_off_level_reply_is_rewritten(client, fake):
    fake.replies = [turn("你要喝量子茶吗？"), turn("要喝？", "Something to drink?")]
    s = client.post("/api/tutor/sessions", json={"scenario": "restaurant"}).json()
    assert "量子" in fake.calls[1]["user"]  # the rewrite names the exact words
    opening = s["turns"][0]
    assert opening["role"] == "tutor" and opening["text"] == "要喝？" and opening["off_level"] == []
    assert opening["hint"] and opening["tokens"][0]["surface"] in ("要", "要喝")
    # Scenario phrases and level words are allowed: the system prompt lists them.
    assert "服务员" in fake.calls[0]["system"] and "Learner's goal" in fake.calls[0]["system"]


def test_mistakes_become_cards_and_goal_is_tracked(client, fake):
    fake.replies = [turn("要喝？")]
    s = client.post("/api/tutor/sessions", json={"scenario": "restaurant"}).json()
    learner = {"original": "我要喝了朋友", "corrected": "我要喝", "english": "I'd like a drink.",
               "errors": [{"category": "extra_word", "wrong": "了朋友", "right": "", "explanation": "Leave this out."}]}
    fake.replies = [turn("我在工作。", "I am working.", learner=learner, goal=True)]
    s = client.post(f"/api/tutor/sessions/{s['id']}/turns", json={"text": "我要喝了朋友"}).json()
    mine, theirs = s["turns"][1], s["turns"][2]
    assert mine["role"] == "learner" and mine["corrected"] == "我要喝"
    assert mine["errors"][0]["label"] == "Extra word" and mine["errors"][0]["card_id"] is None  # nothing to fill in
    assert theirs["text"] == "我在工作。" and s["goal_met"]
    assert next(x for x in client.get("/api/tutor/scenarios").json() if x["id"] == "restaurant")["completed"] == 1

    learner2 = {"original": "我在工作银行", "corrected": "我在银行工作", "english": "I work at a bank.",
                "errors": [{"category": "word_order", "wrong": "工作银行", "right": "银行工作", "explanation": "Place comes before the verb."}]}
    fake.replies = [turn("朋友？", learner=learner2)]
    s = client.post(f"/api/tutor/sessions/{s['id']}/turns", json={"text": "我在工作银行"}).json()
    err = s["turns"][3]["errors"][0]
    assert err["card_id"] is not None
    cloze = [c for c in client.get("/api/reviews/due").json() if c["facet"].startswith("cloze:")]
    assert cloze and cloze[0]["cloze"]["sentence"] == "我在银行工作"
    # The conversation so far is sent as context.
    assert "Learner: 我要喝了朋友" in fake.calls[-1]["user"]

    j = client.get("/api/journal").json()
    assert j["entries"] == [] and j["categories"] == {"extra_word": 1, "word_order": 1}

    ended = client.post(f"/api/tutor/sessions/{s['id']}/end").json()
    assert ended["status"] == "ended"
    assert client.post(f"/api/tutor/sessions/{s['id']}/turns", json={"text": "再见"}).status_code == 409
