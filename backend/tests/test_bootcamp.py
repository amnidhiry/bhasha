import random
from collections import Counter

import pytest

from app.bootcamp import drills, soundbank
from app.importers.cedict import normalize_pinyin

BANK = {f"{syl}{t}": ch for syl, chars in {
    "ma": "妈麻马骂", "shi": "师十使是", "ji": "鸡级几记", "zhi": "知直纸至", "ba": "八拔把爸", "pa": "趴爬  怕",
} .items() for t, ch in zip((1, 2, 3, 4), chars) if ch.strip()}


@pytest.fixture()
def bank(monkeypatch):
    soundbank.reset()
    monkeypatch.setattr(soundbank, "build", lambda db: BANK)
    yield BANK
    soundbank.reset()


def test_hsk_u_umlaut_is_normalized():
    assert normalize_pinyin("lü4 se4") == "lv4 se4"


def test_sound_bank_uses_default_readings(client):
    soundbank.reset()
    with client.session_factory() as s:
        b = soundbank.build(s)
    assert b.get("xing2") == "行" and "hang2" not in b  # 行 alone is read xíng
    soundbank.reset()


def test_tone_drill_items_are_answerable(client, bank):
    items = client.get("/api/bootcamp/drill", params={"drill": "tone", "n": 12}).json()
    assert len(items) == 12
    for it in items:
        assert it["answer"] in [o["value"] for o in it["options"]]
        assert it["audio"]["char"] == BANK[it["item"]]


def test_weak_tones_come_up_more(client, bank):
    # Perfect on tones 1, 2, 4; always wrong on tone 3.
    attempts = [{"drill": "tone", "item": f"ma{t}", "answer": str(t), "correct": t != 3} for t in (1, 2, 3, 4) for _ in range(20)]
    client.post("/api/bootcamp/attempts", json=attempts)
    with client.session_factory() as s:
        counts = Counter(i["answer"] for i in drills.make(s, 1, "tone", 400, seed=7))
    assert counts["3"] > 2 * max(counts["1"], counts["2"], counts["4"])


def test_sandhi_answers_are_spoken_tones(client):
    with client.session_factory() as s:
        items = {i["item"]: i["answer"] for i in drills.sandhi_items(s, 1, 40, random.Random(1))}
    assert items["你好"] == "23" and items["不是"] == "24" and items["一个"] == "24" and items["一起"] == "43"


def test_contrast_drill(client, bank):
    items = client.get("/api/bootcamp/drill", params={"drill": "contrast:zh-j", "n": 6}).json()
    assert items and all(i["answer"] in ("zhi", "ji") for i in items)
    assert all({o["value"] for o in i["options"]} == {"zhi", "ji"} for i in items)
    assert client.get("/api/bootcamp/drill", params={"drill": "contrast:nope"}).status_code == 404


def test_mastery_after_twenty_at_85_percent(client, bank):
    good = [{"drill": "contrast:b-p", "item": "ba4|pa4", "answer": "ba", "correct": i % 10 != 0} for i in range(20)]
    ov = client.post("/api/bootcamp/attempts", json=good).json()
    d = next(x for x in ov["drills"] if x["id"] == "contrast:b-p")
    assert d["attempts"] == 20 and d["accuracy"] == 0.9 and d["mastered"]


def test_tone_perfect_import_and_serving(client, tmp_path, monkeypatch):
    from app.config import get_settings
    from app.importers.toneperfect import import_toneperfect
    root = tmp_path / "toneperfect"
    (root / "mp3").mkdir(parents=True)
    for name in ["ma3_FV1_MP3.mp3", "ma3_MV2_MP3.mp3", "lü4_FV1_MP3.mp3", "readme.mp3"]:
        (root / "mp3" / name).write_bytes(b"ID3fake")
    monkeypatch.setattr(get_settings(), "audio_dir", str(root))
    with client.session_factory() as s:
        assert import_toneperfect(s, root) == (3, 1)
    r = client.get("/api/audio/ma3", params={"speaker": "MV2"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/mpeg" and r.content == b"ID3fake"
    assert client.get("/api/audio/lv4").status_code == 200  # ü filenames indexed as v
    assert client.get("/api/audio/xx9").status_code == 404
    assert client.get("/api/bootcamp").json()["recorded_audio"] is True


def test_bootcamp_overview(client, bank):
    b = client.get("/api/bootcamp").json()
    assert [t["tone"] for t in b["tones"]] == [1, 2, 3, 4, 5]
    assert [e["label"] for e in b["tone_examples"]] == ["mā", "má", "mǎ", "mà"]
    assert any(d["id"] == "contrast:zh-j" for d in b["drills"])
