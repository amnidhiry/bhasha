"""Characters module: component index, variant families, opaque-character notes,
and the learner's characters. Extra Make Me a Hanzi rows (real entries) are added
inside these tests so the shared fixture stays small."""

import pytest
from sqlalchemy import select

from app.characters import compare_sounds, family, parts, split_syllable
from app.models import CharacterInfo, Unit, WordFrequency

# Real Make Me a Hanzi entries (dictionary.txt), trimmed to the fields we store.
EXTRA = [
    ("清", "clear, pure, clean; peaceful", ["qīng"], "⿰氵青",
     {"type": "pictophonetic", "phonetic": "青", "semantic": "氵", "hint": "water"}, "氵"),
    ("青", "nature's color; blue, green, black; young", ["qīng"], "⿱龶月", None, "青"),
    ("氵", "water", ["shuǐ"], "⿱？？", None, "氵"),
    ("水", "water, liquid, lotion, juice", ["shuǐ"], "？", {"type": "pictographic", "hint": "A river running between banks"}, "水"),
    ("泉", "spring, fountain; wealth, money", ["quán"], "⿱白水",
     {"type": "ideographic", "hint": "Water 水 flowing from a spring 白"}, "水"),
    ("月", "moon; month", ["yuè"], "⿵冂二", {"type": "pictographic", "hint": "A crescent moon"}, "月"),
    ("龶", None, [], "？", None, "龶"),
    ("精", "essence; semen; spirit", ["jīng"], "⿰米青",
     {"type": "pictophonetic", "phonetic": "青", "semantic": "米", "hint": "grain"}, "米"),
    ("猜", "guess, conjecture, suppose; feel", ["cāi"], "⿰犭青",
     {"type": "pictophonetic", "phonetic": "青", "semantic": "犭", "hint": "dog"}, "犭"),
    ("汉", "the Han dynasty; the Chinese people", ["hàn"], "⿰氵又",
     {"type": "ideographic", "hint": "Simplified form of 漢; the Han\xa0𦰩\xa0river 氵"}, "氵"),
    ("又", "and, also, again, in addition", ["yòu"], "？",
     {"type": "pictographic", "hint": "A right hand, representing a pair; compare 左"}, "又"),
    ("艮", "blunt; tough, chewy", ["gěn"], "⿸？？", None, "艮"),
    ("钅", "gold, metal; money", ["jīn"], "⿱？？", {"type": "pictographic", "hint": "A cast-iron bell; compare 金"}, "钅"),
    ("们", "adjunct pronoun indicate plural", ["men"], "⿰亻门",
     {"type": "pictophonetic", "phonetic": "门", "semantic": "亻", "hint": "people"}, "亻"),
    ("门", "gate, door, entrance, opening", ["mén"], "？", {"type": "pictographic", "hint": "A door"}, "门"),
    ("问", "ask about, inquire", ["wèn"], "⿵门口",
     {"type": "pictophonetic", "phonetic": "门", "semantic": "口", "hint": "mouth"}, "口"),
]


@pytest.fixture()
def chars(client):
    from app.characters import clear_cache
    with client.session_factory() as s:
        for ch, d, py, dec, ety, rad in EXTRA:
            s.add(CharacterInfo(character=ch, definition=d, pinyin=py, decomposition=dec, radical=rad, etymology=ety))
        for w, pm in [("清楚", 300.0), ("精神", 50.0), ("汉语", 80.0), ("猜", 20.0), ("银行", 90.0), ("我", 9000.0)]:
            s.add(WordFrequency(word=w, rank=1, per_million=pm, cd_percent=1.0))
        s.commit()
    clear_cache()
    yield client
    clear_cache()


def _unit_id(client, head):
    with client.session_factory() as s:
        return s.scalar(select(Unit.id).where(Unit.headword == head, Unit.type == "word"))


# --- Pure helpers ----------------------------------------------------------------

def test_parts_strip_ids_and_unknowns():
    assert parts("⿰钅艮") == ["钅", "艮"]
    assert parts("⿱⿰木木一") == ["木", "木", "一"]
    assert parts("⿱？？") == [] and parts(None) == []


def test_variant_families():
    assert family("氵") == family("水") == "水"
    assert family("扌") == "手" and family("讠") == "言" and family("钅") == family("釒") == "金"
    assert family("亻") == "人" and family("忄") == "心" and family("纟") == "糸"
    assert family("饣") == "食" and family("艹") == "艸" and family("辶") == "辵"
    assert family("青") == "青"


@pytest.mark.parametrize("syl,expected", [
    ("yín", ("", "in")), ("wèn", ("", "uen")), ("mén", ("m", "en")), ("qù", ("q", "v")),
    ("yǔ", ("", "v")), ("zhī", ("zh", "ɨ")), ("jī", ("j", "i")), ("liú", ("l", "iou")), ("lǜ", ("l", "v")),
])
def test_split_syllable(syl, expected):
    assert split_syllable(syl) == expected


@pytest.mark.parametrize("char,part,match", [
    ("qīng", "qīng", "same"),      # 清 / 青
    ("qíng", "qīng", "syllable"),  # 情 / 青
    ("jīng", "qīng", "rhyme"),     # 精 / 青
    ("wèn", "mén", "rhyme"),       # 问 / 门 (w-en is u-en)
    ("yín", "gěn", "none"),        # 银 / 艮
    ("cāi", "qīng", "none"),       # 猜 / 青
    ("hǎi", "měi", "none"),        # 海 / 每
    ("bǎo", "bāo", "syllable"),
    ("pà", "bái", "none"),
    ("zhǐ", "zhí", "syllable"),
    ("hé", "kě", "rhyme"),         # 河 / 可
    ("bàn", "bā", "initial"),
])
def test_compare_sounds(char, part, match):
    assert compare_sounds(char, part) == match


def test_zhi_and_ji_do_not_rhyme():
    assert compare_sounds("zhī", "jī") == "none"


# --- Character page ----------------------------------------------------------------

def test_character_page_flags_misleading_sound_part(chars):
    d = chars.get("/api/characters/银").json()
    assert d["decomposition"] == "⿰钅艮" and d["radical"] == "钅" and d["radical_family"] == "金"
    roles = {p["component"]: p["role"] for p in d["parts"]}
    assert roles == {"钅": "meaning", "艮": "sound"}
    assert d["transparency"] == "opaque"
    sound = next(n for n in d["notes"] if n["kind"] == "sound_misleading")
    assert sound["text"] == "The sound part 艮 (gěn) doesn't hint at yín here."
    assert d["has_strokes"] is True and d["writing"] is False
    assert d["frequency"]["per_million"] == 90.0


def test_character_page_helpful_and_partial_sound_parts(chars):
    qing = chars.get("/api/characters/清").json()
    assert qing["transparency"] == "clear"
    assert any(n["kind"] == "sound_helps" and "青 (qīng)" in n["text"] for n in qing["notes"])
    jing = chars.get("/api/characters/精").json()
    assert jing["transparency"] == "partial"
    assert any("rhymes with jīng" in n["text"] for n in jing["notes"])
    wen = chars.get("/api/characters/问").json()
    assert wen["transparency"] == "partial"
    men = chars.get("/api/characters/们").json()
    assert men["transparency"] == "clear" and "only the tone differs" in men["notes"][-1]["text"]


def test_simplified_meaning_compound_flags_the_unused_part(chars):
    d = chars.get("/api/characters/汉").json()
    assert d["transparency"] == "opaque"
    note = next(n for n in d["notes"] if n["kind"] == "part_misleading")
    assert note["component"] == "又" and "“and”" in note["text"] and "simplification" in note["text"]


def test_explained_compounds_and_missing_etymology_are_not_opaque(chars):
    wo = chars.get("/api/characters/我").json()  # A hand 扌 holding a weapon 戈
    assert wo["transparency"] == "clear"
    qing = chars.get("/api/characters/青").json()  # no etymology in Make Me a Hanzi
    assert qing["transparency"] == "unknown" and qing["notes"][0]["kind"] == "no_etymology"


def test_character_page_lists_your_words(chars):
    chars.post("/api/units/mark", json={"unit_ids": [_unit_id(chars, "银行")], "status": "known"})
    d = chars.get("/api/characters/行").json()
    assert d["status"] == "known"
    assert [w["headword"] for w in d["words"]] == ["银行"] and d["words"][0]["status"] == "known"
    # The standalone word 行 is an HSK word not yet learned: suggested, not listed as yours.
    assert "行" in [w["headword"] for w in d["more_words"]]


def test_unknown_character_404(chars):
    assert chars.get("/api/characters/𠀀").status_code == 404
    assert chars.get("/api/characters/ab").status_code == 400


# --- Component explorer ----------------------------------------------------------------

def test_explorer_merges_variants_and_recurses(chars):
    d = chars.get("/api/components/水", params={"all": "true"}).json()
    found = {c["character"]: c for c in d["characters"]}
    assert {"清", "汉", "泉"} <= set(found)  # 氵 and 水 are one family
    assert d["family"]["key"] == "水" and d["family"]["members"][:1] == ["氵"]

    moon = chars.get("/api/components/月", params={"all": "true"}).json()
    by = {c["character"]: c for c in moon["characters"]}
    assert by["青"]["depth"] == 1 and by["青"]["via"] is None
    assert by["清"]["depth"] == 2 and by["清"]["via"] == "青"  # 清 → 青 → 月
    direct = chars.get("/api/components/月", params={"all": "true", "direct": "true"}).json()
    assert "清" not in {c["character"] for c in direct["characters"]}


def test_explorer_ranks_known_first_then_frequency(chars):
    d = chars.get("/api/components/青").json()
    order = [c["character"] for c in d["characters"]]
    assert order == ["清", "精", "猜"]  # by frequency: 300, 50, 20 per million

    with chars.session_factory() as s:
        for w, r in [("猜", "cai1"), ("精", "jing1")]:
            s.add(Unit(language="zh", type="word", headword=w, reading=r, level_tags=[], track_tags=[], extra={}))
        s.commit()
    chars.post("/api/mine", json={"unit_id": _unit_id(chars, "猜"), "sentence": "你猜。"})  # in reviews: learning
    chars.post("/api/units/mark", json={"unit_ids": [_unit_id(chars, "精")], "status": "known"})
    d = chars.get("/api/components/青").json()
    assert [(c["character"], c["status"]) for c in d["characters"]] == [
        ("精", "known"), ("猜", "learning"), ("清", "new")]
    assert d["counts"] == {"total": 3, "known": 1, "learning": 1}


def test_explorer_hides_rare_characters_unless_asked(chars):
    d = chars.get("/api/components/水").json()
    shown = {c["character"] for c in d["characters"]}
    assert "泉" not in shown and "清" in shown and d["filtered"] is True


def test_explorer_rejects_unknown_component(chars):
    assert chars.get("/api/components/𠀀").status_code == 404


# --- Overview ----------------------------------------------------------------

def test_overview_of_known_characters_grouped_by_component(chars):
    ids = [_unit_id(chars, w) for w in ("银行", "我")]
    chars.post("/api/units/mark", json={"unit_ids": ids, "status": "known"})
    with chars.session_factory() as s:
        for w, r in [("清", "qing1"), ("精", "jing1"), ("汉", "han4")]:
            s.add(Unit(language="zh", type="word", headword=w, reading=r, level_tags=[], track_tags=[], extra={}))
        s.commit()
    with chars.session_factory() as s:
        more = [s.scalar(select(Unit.id).where(Unit.headword == w, Unit.type == "word")) for w in ("清", "精", "汉")]
    chars.post("/api/units/mark", json={"unit_ids": more, "status": "known"})

    d = chars.get("/api/characters").json()
    assert set(c["character"] for c in d["characters"]) == {"银", "行", "我", "清", "精", "汉"}
    assert d["counts"] == {"known": 6, "learning": 0}
    groups = {g["key"]: g for g in d["groups"]}
    assert set(groups["青"]["characters"]) == {"清", "精"}
    assert set(groups["水"]["characters"]) == {"清", "汉"} and groups["水"]["members"][0] == "氵"
    assert set(groups["月"]["characters"]) == {"清", "精"}  # through 青, one level down
    # Overview tiles carry the opaque flag for the grid.
    assert next(c for c in d["characters"] if c["character"] == "银")["transparency"] == "opaque"


def test_index_rebuilds_when_data_changes(chars):
    assert chars.get("/api/characters/泳").status_code == 404
    with chars.session_factory() as s:
        s.add(CharacterInfo(character="泳", definition="dive; swim", pinyin=["yǒng"], decomposition="⿰氵永",
                            radical="氵", etymology={"type": "pictophonetic", "phonetic": "永", "semantic": "氵", "hint": "water"}))
        s.commit()
    assert chars.get("/api/characters/泳").status_code == 200
