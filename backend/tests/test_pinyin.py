import pytest

from app.packs.zh import ZhPack
from app.packs.zh.pinyin import numeric_to_marks


@pytest.mark.parametrize("num,mark", [
    ("hao3", "hǎo"), ("lv4", "lǜ"), ("le5", "le"), ("gou3", "gǒu"), ("gui4", "guì"),
    ("xiong2", "xióng"), ("Bei3", "Běi"), ("er2", "ér"), ("liu2", "liú"), ("lü3", "lǚ"), ("nv3", "nǚ"),
])
def test_tone_marks(num, mark):
    assert numeric_to_marks(num) == mark


def surface(pack, text):
    return [(t.surface, " ".join(s.surface_display for s in t.syllables)) for t in pack.analyze(text) if t.syllables]


def citation(pack, text):
    return [(t.surface, " ".join(s.citation_display for s in t.syllables)) for t in pack.analyze(text) if t.syllables]


@pytest.fixture(scope="module")
def pack():
    return ZhPack()


def test_bu_sandhi_keeps_citation(pack):
    assert ("不是", "bú shì") in surface(pack, "他不是医生。")
    assert ("不是", "bù shì") in citation(pack, "他不是医生。")
    assert ("不吃", "bù chī") in surface(pack, "我不吃。")  # no change before tone 1


def test_yi_sandhi(pack):
    s = dict(surface(pack, "一起去，一个人，第一天。"))
    assert s["一起"] == "yì qǐ"
    assert s["一个"] == "yí gè"
    assert s["第一天"] == "dì yī tiān"


def test_third_tone(pack):
    assert dict(surface(pack, "展览馆"))["展览馆"] == "zhán lán guǎn"
    assert surface(pack, "我很好。") == [("我", "wǒ"), ("很", "hén"), ("好", "hǎo")]


def test_polyphones_per_word(pack):
    s = dict(citation(pack, "我在银行工作，他行走。"))
    assert s["银行"] == "yín háng"
    assert s["行走"] == "xíng zǒu"


def test_dictionary_reading_overrides_when_unambiguous(pack):
    p = ZhPack()
    p.add_words([("朋友", "peng2 you5"), ("行", "hang2"), ("行", "xing2")])
    assert dict(citation(p, "朋友"))["朋友"] == "péng you"
    assert "行" not in p.readings  # polyphone: keep pypinyin's choice


def test_token_kinds_and_sentences(pack):
    toks = pack.analyze("王小明住在北京。我有3本书！")
    kinds = {t.surface: t.kind for t in toks}
    assert kinds["王小明"] == "proper" and kinds["北京"] == "proper"
    assert kinds["3"] == "number" and kinds["。"] == "punct"
    assert [t.sentence_index for t in toks if t.surface in ("北京", "我")] == [0, 1]


def test_split_rules():
    p = ZhPack(split_rules={"银行": ["银", "行"]})
    assert [t.surface for t in p.analyze("银行")] == ["银", "行"]


@pytest.mark.parametrize("sentence,char,reading", [
    ("他跑得很快。", "得", "de5"), ("我得走了。", "得", "dei3"),
    ("慢慢地走。", "地", "de5"), ("在地上。", "地", "di4"),
    ("头发很长。", "长", "chang2"), ("他长得很高。", "长", "zhang3"),
    ("我还你钱。", "还", "huan2"), ("他还没来。", "还", "hai2"),
    ("请重说一遍。", "重", "chong2"), ("这个很重。", "重", "zhong4"),
])
def test_standalone_polyphones_in_context(pack, sentence, char, reading):
    pos = 0
    for t in pack.analyze(sentence):
        if pos <= sentence.index(char) < pos + len(t.surface):
            assert t.syllables[sentence.index(char) - pos].citation == reading, [x.surface for x in pack.analyze(sentence)]
            return
        pos += len(t.surface)
