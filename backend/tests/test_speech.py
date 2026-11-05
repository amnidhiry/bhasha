import importlib
import sys
from pathlib import Path

import httpx
import pytest

np = pytest.importorskip("numpy")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "speech"))


@pytest.fixture()
def speech(client, tmp_path, monkeypatch):
    """bhasha -> HTTP -> the real speech service (synth engine), in-process.
    Host A is down; host B answers; requests are counted."""
    monkeypatch.setenv("SPEECH_ENGINE", "synth")
    monkeypatch.setenv("SPEECH_TOKEN", "tok")
    import bhasha_speech.app as speech_app
    importlib.reload(speech_app)
    from fastapi.testclient import TestClient
    svc = TestClient(speech_app.app)
    calls = {"tts": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.host == "pc.lan":
            raise httpx.ConnectError("PC is off", request=req)
        if req.url.path == "/tts":
            calls["tts"] += 1
        r = svc.request(req.method, req.url.path, content=req.content, headers=dict(req.headers))
        return httpx.Response(r.status_code, content=r.content, headers=r.headers)

    from app import speech
    from app.config import get_settings
    monkeypatch.setattr(speech, "transport", httpx.MockTransport(handler))
    monkeypatch.setattr(speech, "_health", {})
    s = get_settings()
    monkeypatch.setattr(s, "speech_urls", "http://pc.lan:8790,http://speech:8790")
    monkeypatch.setattr(s, "speech_token", "tok")
    monkeypatch.setattr(s, "audio_cache_dir", str(tmp_path / "audio"))
    return calls


def test_no_host_configured_means_device_voice(client):
    r = client.get("/api/tts", params={"text": "你好"})
    assert r.status_code == 503


def test_tts_fails_over_and_caches(client, speech):
    r = client.get("/api/tts", params={"text": "你好"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and "immutable" in r.headers["cache-control"]
    assert client.get("/api/tts", params={"text": "你好"}).content == r.content
    assert speech["tts"] == 1  # second request served from the cache
    st = client.get("/api/speech").json()
    assert [h["online"] for h in st["hosts"]] == [False, True]
    assert st["active"] == "http://speech:8790" and st["voice"] == "tones"


def test_wrong_token_is_reported(client, speech, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "speech_token", "wrong")
    r = client.get("/api/tts", params={"text": "谢谢"})
    assert r.status_code == 503 and "token" in r.json()["detail"]


def test_voice_choice_validated(client, speech):
    assert client.put("/api/speech/voice", json={"voice": "nope"}).status_code == 400
    assert client.put("/api/speech/voice", json={"voice": "tones"}).json()["voice"] == "tones"


def test_tone_check_scores_the_synth_voice(client, speech, monkeypatch):
    from app import jobs
    from app.bootcamp import soundbank
    from tests.test_bootcamp import BANK
    monkeypatch.setattr(soundbank, "build", lambda db: BANK)
    assert client.post("/api/speech/tone-check", json={"voices": ["tones"]}).status_code == 202
    assert jobs.run_once(client.session_factory).status == "done"
    result = client.get("/api/speech").json()["tone_check"]["tones"]
    # Textbook contours: the classifier should hear every tone right.
    assert result["n"] >= 12 and result["accuracy"] == 1.0, result["misses"]


def test_new_texts_are_prerendered(client, speech):
    from app import jobs
    from app.models import AudioClip
    t = client.post("/api/texts/import", json={"title": "t", "body": "我在银行工作。朋友是医生。"}).json()
    assert [j["kind"] for j in client.get("/api/jobs").json()] == ["render_text"]
    assert client.get("/api/jobs", params={"kind": "generate"}).json() == []
    assert jobs.run_once(client.session_factory).result == {"rendered": 2}
    with client.session_factory() as s:
        assert {c.text for c in s.query(AudioClip)} == {"我在银行工作。", "朋友是医生。"}
    assert speech["tts"] == 2
    # Playing a sentence in the reader is now a cache hit.
    client.get("/api/tts", params={"text": "我在银行工作。"})
    assert speech["tts"] == 2
