import io
import wave

import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("SPEECH_ENGINE", "synth")
    monkeypatch.setenv("SPEECH_TOKEN", "s3cret")
    import importlib

    import bhasha_speech.app as app_mod
    importlib.reload(app_mod)
    from fastapi.testclient import TestClient
    return TestClient(app_mod.app)


AUTH = {"Authorization": "Bearer s3cret"}


def test_health_names_engine_and_voices(client):
    h = client.get("/health").json()
    assert h["engine"] == "synth" and h["voices"] == ["tones"] and h["device"] == "cpu"


def test_tts_returns_playable_wav(client):
    r = client.post("/tts", json={"text": "你好"}, headers=AUTH)
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    with wave.open(io.BytesIO(r.content)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 24000)
        assert 0.8 < w.getnframes() / 24000 < 1.3  # two syllables
    assert r.headers["x-voice"] == "tones"


def test_token_required(client):
    assert client.post("/tts", json={"text": "你好"}).status_code == 401
    assert client.post("/tts", json={"text": "你好"}, headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_limits(client):
    assert client.post("/tts", json={"text": "好" * 401}, headers=AUTH).status_code == 422
    assert client.post("/tts", json={"text": "你好", "voice": "nope"}, headers=AUTH).status_code == 400
    assert client.post("/tts", json={"text": "你好", "speed": 3}, headers=AUTH).status_code == 422
