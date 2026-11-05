import pytest

from app.llm import gateway
from app.llm.providers import FakeProvider


def _bank_card(client):
    t = client.post("/api/texts/import", json={"title": "t", "body": "我在银行工作。"}).json()
    bank = next(w for w in t["tokens"] if w["surface"] == "银行")
    return client.post("/api/mine", json={"unit_id": bank["unit_id"], "text_id": t["id"], "sentence": "我在银行工作。",
                                          "facets": ["meaning"]}).json()["created"][0]["card_id"]


def test_help_shows_parts_with_roles(client):
    h = client.get(f"/api/cards/{_bank_card(client)}/help").json()
    yin = h["characters"][0]
    assert yin["char"] == "银"
    roles = {p["part"]: p["role"] for p in yin["parts"]}
    assert roles == {"钅": "meaning", "艮": "sound"}
    assert h["mnemonic"] is None and h["examples"] == []


def test_mnemonic_uses_real_components_and_is_kept(client, monkeypatch):
    fake = FakeProvider(replies=[{"mnemonic": "Metal 钅 money is kept in a bank."}])
    monkeypatch.setattr(gateway, "override", fake)
    cid = _bank_card(client)
    assert client.post(f"/api/cards/{cid}/mnemonic").json()["mnemonic"].startswith("Metal")
    prompt = fake.calls[0]["user"]
    assert "钅 = " in prompt and "(meaning part)" in prompt and "艮 = " in prompt and "(sound part)" in prompt
    assert client.get(f"/api/cards/{cid}/help").json()["mnemonic"].startswith("Metal")


def test_suspend_removes_from_queue(client):
    cid = _bank_card(client)
    assert any(c["card_id"] == cid for c in client.get("/api/reviews/due").json())
    client.post(f"/api/cards/{cid}/suspend", json={"suspended": True})
    assert not any(c["card_id"] == cid for c in client.get("/api/reviews/due").json())
