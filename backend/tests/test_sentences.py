from pathlib import Path

import pytest

from app.importers.subtlex import import_subtlex
from app.importers.tatoeba import import_tatoeba

FX = Path(__file__).parent / "fixtures"


@pytest.fixture()
def data(client):
    with client.session_factory() as s:
        import_subtlex(s, FX / "subtlex_sample.txt")
        n = import_tatoeba(s, FX / "tatoeba" / "cmn_sentences.tsv.bz2", FX / "tatoeba" / "eng_sentences.tsv",
                           FX / "tatoeba" / "cmn-eng_links.tsv")
    return n


@pytest.mark.parametrize("name", ["subtlex_sample.txt", "subtlex_sample_gbk.txt"])
def test_subtlex_parses_utf8_and_gbk(client, name):
    from app.models import WordFrequency
    with client.session_factory() as s:
        assert import_subtlex(s, FX / name) == 7
        assert s.get(WordFrequency, ("zh", "我")).rank == 1 and s.get(WordFrequency, ("zh", "量子")).rank == 7


def test_subtlex_fills_missing_ranks_only(client):
    from sqlalchemy import select
    from app.models import Unit
    with client.session_factory() as s:
        s.add(Unit(language="zh", type="word", headword="医生", reading="yi1 sheng1", extra={"source": "segmenter"}))
        s.commit()
        import_subtlex(s, FX / "subtlex_sample.txt")
        doctor = s.scalar(select(Unit).where(Unit.headword == "医生"))
        bank = s.scalar(select(Unit).where(Unit.headword == "银行"))
        assert doctor.frequency_rank == 5     # filled from SUBTLEX (ranked by count)
        assert bank.frequency_rank == 2000    # HSK rank kept


def test_tatoeba_keeps_simplified_translated_sentences(client, data):
    from app.models import ExampleSentence
    with client.session_factory() as s:
        texts = sorted(x.text for x in s.query(ExampleSentence))
    # 103 is Traditional (銀), 105 has no translation, 106 is English, 107 is too short.
    assert data == 3 and texts == sorted(["我在银行工作。", "我的朋友是医生。", "朋友在银行工作吗？"])


def test_lookup_shows_examples_and_frequency(client, data):
    r = client.get("/api/lookup", params={"q": "银行"}).json()
    assert r["frequency"]["rank"] == 6
    assert {e["text"] for e in r["examples"]} == {"我在银行工作。", "朋友在银行工作吗？"}
    assert r["examples"][0]["url"].startswith("https://tatoeba.org/en/sentences/show/")


def test_examples_rank_by_what_you_know(client, data):
    client.post("/api/units/mark", json={"status": "known", "level_tag": "hsk3-2025:1"})  # 我 在 工作 朋友
    bank = client.get("/api/lookup", params={"q": "银行"}).json()["units"][0]["id"]
    ex = client.get(f"/api/units/{bank}/examples").json()
    # 我在银行工作 is fully known apart from 银行 itself; the question adds 吗.
    assert ex[0]["text"] == "我在银行工作。" and ex[0]["coverage"] == 1.0


def test_sentences_text_at_your_level(client, data):
    client.post("/api/units/mark", json={"status": "known", "level_tag": "hsk3-2025:1"})
    t = client.post("/api/texts/sentences", json={"n": 3}).json()
    assert t["provenance"] == "tatoeba" and len(t["meta"]["sentences"]) == 3
    assert t["meta"]["sentences"][0]["url"].startswith("https://tatoeba.org/")
    assert t["meta"]["sentence_map"] == [0, 1, 2]
    # A second text never repeats sentences; with only three imported, nothing is left.
    again = client.post("/api/texts/sentences", json={"n": 3})
    assert again.status_code == 409 and "every imported sentence" in again.json()["detail"]


def test_sentences_text_without_data(client):
    r = client.post("/api/texts/sentences", json={"n": 3})
    assert r.status_code == 409 and "No example sentences" in r.json()["detail"]
