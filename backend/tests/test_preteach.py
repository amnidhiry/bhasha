from app import jobs
from app.llm import gateway
from app.llm.providers import FakeProvider
from tests.test_generator import story


def test_pre_teach_picks_repeated_new_words_and_links_texts(client, monkeypatch):
    client.post("/api/units/mark", json={"status": "known", "level_tag": "hsk3-2025:1"})  # 我 在 工作 朋友
    t = client.post("/api/texts/import", json={"title": "银行", "body": "我在银行工作。银行很大。医生在银行。"}).json()
    s = client.get(f"/api/texts/{t['id']}/pre-teach").json()
    assert s["words"][0] == "银行"  # appears three times
    fake = FakeProvider(replies=[story(("我在银行工作。", "I work at a bank."), targets=s["words"])])
    monkeypatch.setattr(gateway, "override", fake)
    r = client.post(f"/api/texts/{t['id']}/pre-teach")
    assert r.status_code == 202
    # Render jobs are queued for the import too; run until the generate job is done.
    while (j := jobs.run_once(client.session_factory)) is not None:
        if j.kind == "generate":
            assert j.status == "done", j.error
            warm = client.get(f"/api/texts/{j.result['text_id']}").json()
    assert warm["title"].startswith("热身") and warm["meta"]["pre_teach_for"]["id"] == t["id"]
    assert client.get(f"/api/texts/{t['id']}").json()["meta"]["pre_teach"]["id"] == warm["id"]
    assert "TARGET WORDS: 银行" in fake.calls[0]["user"]


def test_nothing_to_pre_teach(client):
    client.post("/api/units/mark", json={"status": "known", "level_tag": "hsk3-2025:1"})
    t = client.post("/api/texts/import", json={"title": "x", "body": "我在工作。"}).json()
    assert client.get(f"/api/texts/{t['id']}/pre-teach").json()["words"] == []
    assert client.post(f"/api/texts/{t['id']}/pre-teach").status_code == 409
