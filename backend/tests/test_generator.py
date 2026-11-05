import pytest

from app.generator import _covered, check, Brief
from app.llm import gateway
from app.llm.providers import FakeProvider


def story(*sentences, targets=("银行",)):
    return {"title": "工作", "title_en": "Work", "target_words_used": list(targets),
            "sentences": [{"text": zh, "en": en} for zh, en in sentences],
            "questions": [{"question": "我在哪儿工作？", "question_en": "Where do I work?", "answer_en": "At a bank."}]}


@pytest.fixture()
def fake(monkeypatch):
    f = FakeProvider()
    monkeypatch.setattr(gateway, "override", f)
    return f


def test_covered_splits_merged_tokens():
    allowed = {"我", "们", "很", "好", "的"}
    assert _covered("很好", allowed) and _covered("我们的", allowed) and not _covered("银行", allowed)


def test_check_flags_unknown_and_too_many_new():
    b = Brief(language="zh", topic="", genre="story", sentences=6, known=["我", "在", "工作"], pool=["朋友"], level="1",
              targets=["银行"], max_new=0)
    r = check(b, ["我在银行工作。", "朋友在量子银行工作。"])
    assert r.out_of_bounds == ["量子"]
    assert r.new_words == ["朋友"] and r.too_many_new


def test_generate_repairs_then_stores(client, fake):
    fake.replies = [
        story(("我在量子银行工作。", "I work at a quantum bank.")),
        story(("我在银行工作。", "I work at a bank."), ("朋友在银行工作。", "My friend works at a bank.")),
    ]
    r = client.post("/api/texts/generate", json={"topic": "work", "targets": ["银行"], "length": "short"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["provenance"] == "generated" and t["title"] == "工作"
    assert t["meta"]["attempts"] == 2 and not t["meta"]["accepted_with_issues"]
    assert "量子" in fake.calls[1]["user"]  # the repair names the exact word
    assert t["meta"]["sentence_map"] == [0, 1]
    assert [s["en"] for s in t["meta"]["sentences"]][0] == "I work at a bank."
    # Pinyin comes from local data, never the model.
    bank = next(x for x in t["tokens"] if x["surface"] == "银行")
    assert [s["surface_display"] for s in bank["syllables"]] == ["yín", "háng"]
    # Beginner brief: level-1 words offered, target named.
    assert "朋友" in fake.calls[0]["system"] and "TARGET WORDS: 银行" in fake.calls[0]["user"]


def test_generate_accepts_after_two_failed_repairs(client, fake):
    bad = story(("我在量子银行工作。", "x"))
    fake.replies = [bad, bad, bad]
    t = client.post("/api/texts/generate", json={"topic": "work", "targets": ["银行"]}).json()
    assert t["meta"]["attempts"] == 3 and t["meta"]["accepted_with_issues"]
    assert t["meta"]["out_of_bounds"] == ["量子"]


def test_generate_without_connection_says_how_to_connect(client):
    r = client.post("/api/texts/generate", json={"topic": "x"})
    assert r.status_code == 409 and "Sign in with ChatGPT" in r.json()["detail"]


def test_daily_cap(client, fake, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "llm_max_calls_per_day", 1)
    fake.replies = [story(("我在量子银行工作。", "x")), story(("我在银行工作。", "y"))]
    r = client.post("/api/texts/generate", json={"topic": "work", "targets": ["银行"]})
    assert r.status_code == 429 and "cap" in r.json()["detail"]


def test_flag_sentence(client, fake):
    fake.replies = [story(("我在银行工作。", "I work at a bank."))]
    t = client.post("/api/texts/generate", json={"topic": "work", "targets": ["银行"]}).json()
    flags = client.post(f"/api/texts/{t['id']}/flag", json={"sentence": 0, "note": "odd"}).json()["flags"]
    assert flags[0]["sentence"] == 0
    assert client.get(f"/api/texts/{t['id']}").json()["meta"]["flags"][0]["note"] == "odd"


def test_gateway_refreshes_due_chatgpt_token(client, monkeypatch):
    import time
    from app.llm import chatgpt_auth, providers
    from app.models import LlmConnection
    from app.secrets import encrypt
    from tests.fake_openai import FakeOpenAI, text_events
    import json
    f = FakeOpenAI()
    monkeypatch.setattr(chatgpt_auth, "transport", f.transport())
    monkeypatch.setattr(providers, "transport", f.transport())
    f.stream_events = text_events(json.dumps(story(("我在银行工作。", "I work at a bank."))))
    expired = chatgpt_auth.TokenSet("cid", "old", "refresh-1", "idt", time.time() - 10, "acct")
    with client.session_factory() as s:
        s.add(LlmConnection(kind="chatgpt", label="ChatGPT", base_url="https://api.openai.com/v1",
                            model="gpt-plan-main", ciphertext=encrypt(expired.to_json()), active=True))
        s.commit()
    r = client.post("/api/texts/generate", json={"topic": "work", "targets": ["银行"]})
    assert r.status_code == 200, r.text
    assert f.refreshes == 1
    assert f.requests[-1].headers["authorization"] == "Bearer access-2"
