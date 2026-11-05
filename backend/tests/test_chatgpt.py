import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.llm import chatgpt_auth, providers
from app.llm.errors import PlanLimitError
from app.llm.providers import ChatGPTPlanProvider
from tests.fake_openai import CLIENT_ID, FakeOpenAI, text_events


@pytest.fixture()
def fake(monkeypatch):
    f = FakeOpenAI()
    monkeypatch.setattr(chatgpt_auth, "transport", f.transport())
    monkeypatch.setattr(providers, "transport", f.transport())
    return f


def _callback(flow, **extra):
    q = {"code": "the-code", "state": flow.pkce.state, "client_id": CLIENT_ID, **extra}
    return "http://127.0.0.1:1455/callback?" + "&".join(f"{k}={v}" for k, v in q.items())


def test_authorize_url():
    flow = chatgpt_auth.start()
    q = {k: v[0] for k, v in parse_qs(urlsplit(flow.url).query).items()}
    assert flow.url.startswith("https://auth.openai.com/api/accounts/authorize?")
    assert q["client_id"] == "dynamic_agent_client" and q["agent_name_hint"] == "bhasha"
    assert "chatgpt.tokens.use.direct" in q["scope"].split()
    assert q["redirect_uri"] == "http://127.0.0.1:1455/callback"
    assert q["code_challenge_method"] == "S256" and q["resource"] == "https://api.openai.com/v1"
    assert q["ext_agent_host_id"].startswith("urn:uuid:")


def test_finish_exchanges_code_and_verifies_id_token(fake):
    flow = chatgpt_auth.start()
    fake.nonce = flow.pkce.nonce
    tokens = chatgpt_auth.finish(flow.id, _callback(flow))
    assert (tokens.client_id, tokens.access_token, tokens.email) == (CLIENT_ID, "access-1", "abe@example.com")
    form = parse_qs(next(r for r in fake.requests if r.url.path.endswith("/token")).content.decode())
    assert form["code_verifier"] == [flow.pkce.verifier] and form["grant_type"] == ["authorization_code"]


def test_finish_rejects_bad_addresses(fake):
    flow = chatgpt_auth.start()
    fake.nonce = flow.pkce.nonce
    with pytest.raises(chatgpt_auth.SignInFailedError, match="different sign-in"):
        chatgpt_auth.finish(flow.id, _callback(flow).replace(flow.pkce.state, "other"))
    with pytest.raises(chatgpt_auth.SignInFailedError, match="127.0.0.1"):
        chatgpt_auth.finish(flow.id, "https://example.com/elsewhere")


def test_finish_requires_plan_scope(monkeypatch):
    f = FakeOpenAI(scope="openid offline_access")
    monkeypatch.setattr(chatgpt_auth, "transport", f.transport())
    flow = chatgpt_auth.start()
    f.nonce = flow.pkce.nonce
    with pytest.raises(chatgpt_auth.SignInFailedError, match="plan usage"):
        chatgpt_auth.finish(flow.id, _callback(flow))


def test_finish_rejects_wrong_nonce(fake):
    flow = chatgpt_auth.start()
    fake.nonce = "someone-elses-nonce"
    with pytest.raises(chatgpt_auth.SignInFailedError, match="different sign-in"):
        chatgpt_auth.finish(flow.id, _callback(flow))


def test_responses_stream_strips_refused_fields_and_parses(fake):
    fake.stream_events = text_events(json.dumps({"ok": True}))
    p = ChatGPTPlanProvider("https://api.openai.com/v1", lambda force: "tok")
    out = p.complete_json("gpt-plan-main", "sys", "user", {"type": "object"}, cache_key="k")
    assert out.data == {"ok": True} and out.cached_tokens == 1000
    body = json.loads(fake.requests[-1].content)
    assert body["store"] is False and body["stream"] is True
    assert body["input"][0]["role"] == "developer"
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["prompt_cache_key"] == "k" and "temperature" not in body and "max_output_tokens" not in body


def test_401_refreshes_token_once(fake):
    fake.unauthorized_once = True
    fake.stream_events = text_events("{}")
    forced = []
    p = ChatGPTPlanProvider("https://api.openai.com/v1", lambda force: forced.append(force) or "tok")
    p.complete_json("m", "s", "u", {})
    assert forced == [False, True]


def test_usage_limit_is_a_plan_limit(fake):
    fake.responses_status = 429
    fake.responses_error = {"error": {"code": "subscription_sharing_usage_limit_exceeded", "message": "limit"}}
    p = ChatGPTPlanProvider("https://api.openai.com/v1", lambda force: "tok")
    with pytest.raises(PlanLimitError):
        p.complete_json("m", "s", "u", {})


def test_incomplete_stream_is_an_error(fake):
    fake.stream_events = [{"type": "response.output_text.delta", "delta": "{\"a\""}]
    p = ChatGPTPlanProvider("https://api.openai.com/v1", lambda force: "tok")
    with pytest.raises(Exception, match="ended before"):
        p.complete_json("m", "s", "u", {})


def test_sign_in_through_the_api_stores_encrypted_tokens(client, fake):
    start = client.post("/api/llm/chatgpt/start").json()
    flow = chatgpt_auth._flows[start["flow_id"]]
    fake.nonce = flow.pkce.nonce
    st = client.post("/api/llm/chatgpt/finish", json={"flow_id": flow.id, "address": _callback(flow)}).json()
    assert st["connected"] and st["email"] == "abe@example.com" and st["model"] == "gpt-plan-main"
    from sqlalchemy import select
    from app.models import LlmConnection
    with client.session_factory() as s:
        conn = s.scalar(select(LlmConnection))
        assert "refresh-1" not in conn.ciphertext  # encrypted at rest
    assert [m["id"] for m in client.get("/api/llm/models").json()] == ["gpt-plan-main"]
    assert client.post("/api/llm/signout").json()["connected"] is False
