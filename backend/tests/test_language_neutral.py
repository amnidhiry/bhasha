"""The core is language-neutral: a toy pack runs through the whole flow.

"xx" is a made-up space-delimited language with one inflection (a plural -s
whose lemma drops it) and a romanization that upper-cases words. It has no
pinyin, no characters and no tones, so anything Mandarin-shaped that is still
hard-coded in the core shows up here. A second test keeps core modules from
importing the Mandarin pack's internals.
"""

import ast
from pathlib import Path

import pytest

from app.llm import gateway
from app.llm.providers import FakeProvider
from app.packs import register, unregister
from app.packs.base import PUNCT, WORD, LanguagePack, LevelFramework, Morph, PromptProfile, Scenario, Syllable, Token


class ToyPack(LanguagePack):
    code = "xx"
    name = "Toy"
    adjective = "Toy"
    bcp47 = "xx"
    terminators = ".!?"
    levels = LevelFramework(tag_prefix="xx-test", levels=["A1", "A2"], name="Toy CEFR")
    prompts = PromptProfile(language_name="Toy", list_joiner=", ",
                            error_categories={"word_choice": "Word choice", "ending": "Ending", "grammar": "Grammar"})
    attribution = "toy data"
    subtitle_codes = frozenset({"xx", "toy"})

    def analyze(self, text: str) -> list[Token]:
        out, sentence = [], 0
        for raw in text.replace(".", " . ").replace("?", " ? ").split():
            if raw in ".?":
                out.append(Token(raw, PUNCT, sentence))
                sentence += 1
                continue
            lemma = raw[:-1] if raw.endswith("s") and len(raw) > 3 else None
            morph = [Morph(segment="s", grammar_key="xx-gram:plural")] if lemma else []
            sy = [Syllable(raw, raw.upper(), raw.upper(), raw.upper(), raw.upper(), traps=[(0, 1, "silent")] if raw[0] == "k" else [])]
            out.append(Token(raw, WORD, sentence, syllables=sy, lemma=lemma, morph=morph))
        return out

    def reading(self, word: str) -> str:
        return word.upper()

    def unit_key(self, tok: Token) -> tuple[str, str, str]:
        return ("word", tok.head, self.reading(tok.head))

    def sub_units(self, word: str) -> list[str]:
        return list(word)

    def scenarios(self) -> list:
        return [Scenario(id="market", title="At the market", title_native="marka", setting="A stall.",
                         tutor_role="a stall keeper", goal="Buy two apples.", twist="Apples run out.",
                         phrases=("apel",))]


@pytest.fixture()
def toy(client, monkeypatch):
    register("xx", "Toy", ToyPack)
    from app.bootstrap import ensure_defaults
    from app.models import DictionaryEntry, Unit

    with client.session_factory() as s:
        ensure_defaults(s)
        s.add_all([
            Unit(language="xx", type="word", headword="kat", reading="KAT", level_tags=["xx-test:A1"], track_tags=[],
                 extra={"meanings": ["cat"]}),
            Unit(language="xx", type="word", headword="sit", reading="SIT", level_tags=["xx-test:A1"], track_tags=[], extra={}),
            Unit(language="xx", type="word", headword="apel", reading="APEL", level_tags=["xx-test:A2"], track_tags=[], extra={}),
            DictionaryEntry(language="xx", source="toy-dict", headword="sit", reading="SIT", pos="verb",
                            glosses=["to sit"], tags=[], license="CC0"),
        ])
        s.commit()
    assert client.put("/api/me", json={"active_language": "xx"}).status_code == 200
    fake = FakeProvider()
    monkeypatch.setattr(gateway, "override", fake)
    yield fake
    unregister("xx")


def test_languages_and_me(client, toy):
    langs = {m["code"]: m for m in client.get("/api/languages").json()}
    assert set(langs) == {"zh", "xx"}
    assert langs["zh"]["reading_aid"] == "pinyin" and "tonecheck" in langs["zh"]["features"]
    assert langs["xx"]["features"] == [] and langs["xx"]["levels"]["levels"] == ["A1", "A2"]
    assert client.get("/api/me").json()["active_language"] == "xx"
    assert client.put("/api/me", json={"active_language": "qq"}).status_code == 400


def test_reader_lemmas_lookup_and_review(client, toy):
    t = client.post("/api/texts/import", json={"title": "Toy", "body": "kats sit. apels sit?"}).json()
    assert t["language"] == "xx"
    words = [x for x in t["tokens"] if x["kind"] == WORD]
    kats = words[0]
    assert kats["surface"] == "kats" and kats["lemma"] == "kat" and kats["morph"][0]["grammar_key"] == "xx-gram:plural"
    assert kats["syllables"][0]["traps"] == [[0, 1, "silent"]] or kats["syllables"][0]["traps"] == [(0, 1, "silent")]
    # The inflected form is learned as its lemma: kats and kat share a unit.
    from app.models import Unit
    with client.session_factory() as s:
        kat = s.query(Unit).filter_by(language="xx", headword="kat").one()
    assert kats["unit_id"] == kat.id
    # Only xx texts are listed while xx is active.
    assert [x["id"] for x in client.get("/api/texts").json()] == [t["id"]]

    lk = client.get("/api/lookup", params={"q": "sits"}).json()
    assert lk["query"] == "sit" and lk["form"] == "sits" and lk["dictionary"][0]["glosses"] == ["to sit"]
    assert lk["reading"]["citation_display"] == "SIT" and "cedict" not in lk and lk["attribution"] == "toy data"

    r = client.post("/api/mine", json={"unit_id": kat.id, "text_id": t["id"], "facets": ["meaning"]})
    assert r.status_code == 200, r.text
    assert client.post("/api/mine", json={"unit_id": kat.id, "text_id": t["id"], "facets": ["tone"]}).status_code == 400
    due = client.get("/api/reviews/due").json()
    assert [(c["headword"], c["language"], c["reading_display"], c["meanings"]) for c in due] == [("kat", "xx", "KAT", ["cat"])]

    # Switching back to Mandarin hides the toy cards and texts.
    client.put("/api/me", json={"active_language": "zh"})
    assert client.get("/api/reviews/due").json() == [] and client.get("/api/texts").json() == []
    client.put("/api/me", json={"active_language": "xx"})

    p = client.get("/api/progress").json()
    assert p["framework"] == "Toy CEFR" and [lv["level"] for lv in p["level_cumulative"]] == ["A1", "A2"]
    assert "known_characters" not in p and p["read_unit"] == "words"


def test_generator_journal_and_tutor_use_the_pack(client, toy):
    # apel is an A2 word, outside the A1 pool: the generator asks for a rewrite naming it.
    story = {"title": "kat", "title_en": "Cat", "target_words_used": [], "questions": [],
             "sentences": [{"text": "kat sit", "en": "The cat sits."}, {"text": "apel sit.", "en": "An apple sits."}]}
    toy.replies = [story, {**story, "sentences": story["sentences"][:1]}]
    r = client.post("/api/texts/generate", json={"topic": "cats", "length": "short"})
    assert r.status_code == 200, r.text
    assert "Toy" in toy.calls[0]["system"] and "Toy CEFR" in toy.calls[0]["system"] and "HSK" not in toy.calls[0]["system"]
    assert "apel" in toy.calls[1]["user"]
    assert r.json()["language"] == "xx" and r.json()["meta"]["sentences"] == [{"text": "kat sit.", "en": "The cat sits."}]

    toy.replies = [{"comment": "Good.", "sentences": [{"original": "kat sits.", "corrected": "kat sit.", "english": "The cat sits.",
                                                       "errors": [{"category": "ending", "wrong": "sits", "right": "sit",
                                                                   "explanation": "No ending here."}]}]}]
    e = client.post("/api/journal", json={"text": "kat sits."}).json()
    from app import jobs
    assert jobs.run_once(client.session_factory).status == "done"
    e = client.get(f"/api/journal/{e['id']}").json()
    assert e["status"] == "done" and e["language"] == "xx", e
    assert e["errors"][0]["label"] == "Ending" and e["errors"][0]["card_id"]
    assert toy.calls[-1]["schema"]["properties"]["sentences"]["items"]["properties"]["errors"]["items"]["properties"][
        "category"]["enum"] == ["word_choice", "ending", "grammar"]

    sc = client.get("/api/tutor/scenarios").json()
    assert [(x["id"], x["title_native"]) for x in sc] == [("market", "marka")]
    toy.replies = [{"learner": {"original": "", "corrected": "", "english": "", "errors": []},
                    "reply": {"text": "apel?", "en": "Apple?"}, "goal_met": False, "hint": "Ask for two."}]
    s = client.post("/api/tutor/sessions", json={"scenario": "market"}).json()
    assert s["language"] == "xx" and s["turns"][0]["text"] == "apel?" and s["turns"][0]["off_level"] == []
    assert "a stall keeper" in toy.calls[-1]["system"] and "Mandarin" not in toy.calls[-1]["system"]


def test_importer_uses_the_pack(client, toy):
    srt = b"1\n00:00:01,000 --> 00:00:02,000\nkat sit.\n\n2\n00:00:03,000 --> 00:00:04,000\napel sit.\n"
    r = client.post("/api/import/subtitles/preview", files={"file": ("toy.srt", srt)}, data={"title": "Toy film"})
    assert r.status_code == 200, r.text
    assert "kat sit." in r.json()["parts"][0]["body"]


# --- Architecture -----------------------------------------------------------------

CORE = Path(__file__).resolve().parents[1] / "app"
FORBIDDEN = ("app.packs.zh", "pypinyin", "jieba")
# Mandarin feature modules and importers: they are allowed to use the zh pack directly.
ZH_FEATURES = {
    "bootcamp", "tonecheck.py", "characters.py", "units.py", "packs/zh", "packs/__init__.py",
    "importers/hsk.py", "importers/cedict.py", "importers/hanzi.py", "importers/hanzi_graphics.py",
    "importers/handwriting.py", "importers/toneperfect.py", "importers/subtlex.py", "importers/tatoeba.py",
    "api/bootcamp.py", "api/characters.py", "api/handwriting.py", "api/cards.py",
}


def _allowed(rel: str) -> bool:
    return any(rel == f or rel.startswith(f + "/") for f in ZH_FEATURES)


def test_core_does_not_import_the_mandarin_pack():
    offenders = []
    for path in CORE.rglob("*.py"):
        rel = path.relative_to(CORE).as_posix()
        if _allowed(rel):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            offenders += [f"{rel}: {n}" for n in names if n.startswith(FORBIDDEN)]
    assert offenders == []
