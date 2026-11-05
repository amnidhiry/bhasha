import pytest

from app import jobs
from app.llm import gateway
from app.llm.providers import FakeProvider

TEXT = "我在银行工作了。我有一个朋友，他是医生。我昨天去朋友家。"

CORRECTION = {
    "comment": "Nice work! Watch 了 with habitual actions.",
    "sentences": [
        {"original": "我在银行工作了。", "corrected": "我在银行工作。", "english": "I work at a bank.",
         "errors": [{"category": "aspect_particle", "wrong": "工作了", "right": "工作",
                     "explanation": "No 了 for something you do regularly."}]},
        {"original": "我有一个朋友，他是医生。", "corrected": "我有一个朋友，他是医生。", "english": "I have a friend; he is a doctor.",
         "errors": []},
        {"original": "我昨天去朋友家。", "corrected": "我昨天去了朋友家。", "english": "Yesterday I went to my friend's home.",
         "errors": [
             {"category": "aspect_particle", "wrong": "", "right": "了", "explanation": "Add 了: the visit is completed."},
             # Invented by the model: "银行员" isn't in the text. Must be dropped.
             {"category": "word_choice", "wrong": "银行员", "right": "职员", "explanation": "hallucinated"},
         ]},
    ],
}


@pytest.fixture()
def fake(monkeypatch):
    f = FakeProvider()
    monkeypatch.setattr(gateway, "override", f)
    return f


def test_prompt_suggests_words_and_an_idea(client):
    p = client.get("/api/journal/prompt").json()
    assert p["idea"] and isinstance(p["words"], list)


def test_write_requires_a_model(client):
    assert client.post("/api/journal", json={"text": TEXT}).status_code == 409


def test_correction_verifies_errors_and_makes_cloze_cards(client, fake):
    fake.replies = [CORRECTION]
    e = client.post("/api/journal", json={"text": TEXT}).json()
    assert e["status"] == "queued"
    assert jobs.run_once(client.session_factory).status == "done"
    e = client.get(f"/api/journal/{e['id']}").json()
    assert e["status"] == "done" and e["corrected"] == "我在银行工作。我有一个朋友，他是医生。我昨天去了朋友家。"
    assert [x["right"] for x in e["errors"]] == ["工作", "了"]  # the hallucinated one is gone
    assert e["comment"].startswith("Nice work")
    assert "HSK" in fake.calls[0]["system"] and fake.calls[0]["user"] == TEXT

    due = client.get("/api/reviews/due").json()
    clozes = [c for c in due if c["facet"].startswith("cloze:")]
    # Two cards on the same unit would be siblings; 工作 and 了 are different units.
    assert {c["cloze"]["answer"] for c in clozes} == {"工作", "了"}
    added = next(c for c in clozes if c["cloze"]["answer"] == "了")
    assert added["cloze"]["sentence"] == "我昨天去了朋友家。" and added["cloze"]["wrong"] == ""
    assert added["headword"] == "了"  # aspect errors attach to the particle

    stats = client.get("/api/journal").json()
    assert stats["categories"] == {"aspect_particle": 2}


def test_unchanged_sentence_ignores_listed_errors(client, fake):
    fake.replies = [{"comment": "", "sentences": [
        {"original": "我是医生。", "corrected": "我是医生。", "english": "I am a doctor.",
         "errors": [{"category": "grammar", "wrong": "是", "right": "是", "explanation": "x"}]}]}]
    e = client.post("/api/journal", json={"text": "我是医生。"}).json()
    jobs.run_once(client.session_factory)
    assert client.get(f"/api/journal/{e['id']}").json()["errors"] == []


def test_failed_correction_can_be_retried(client, fake):
    from app.llm.errors import PlanLimitError

    def limited(_):
        raise PlanLimitError()
    fake.replies = [limited, CORRECTION]
    e = client.post("/api/journal", json={"text": TEXT}).json()
    assert jobs.run_once(client.session_factory).status == "failed"
    got = client.get(f"/api/journal/{e['id']}").json()
    assert got["status"] == "failed" and "usage limit" in got["error"]
    assert client.post(f"/api/journal/{e['id']}/retry").json()["status"] == "queued"
    jobs.run_once(client.session_factory)
    assert client.get(f"/api/journal/{e['id']}").json()["status"] == "done"
