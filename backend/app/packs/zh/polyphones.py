"""Context rules for single-character polyphones that the segmenter leaves on
their own, where pypinyin falls back to the most common reading.

Measured on 28 sentences (single characters and characters inside words),
neither pypinyin nor g2pM was reliable for standalone 得, 地, 长, 还 and 重
(both 6/14 on standalone characters; g2pM was worse inside words, 8/14 vs
11/14), so instead of a model we use a few explicit rules for these very
frequent learner-facing words. Each rule looks only at the neighbouring
tokens and their jieba part-of-speech tags; when unsure it returns None and
the default reading stands."""

DEGREE = {"很", "太", "真", "非常", "多", "这么", "那么", "特别", "比较", "更", "最", "挺", "不", "多么", "够"}
HUAN_OBJECTS = {"你", "我", "他", "她", "它", "你们", "他们", "我们", "钱", "给", "书", "他的", "你的"}

Neighbour = tuple[str, str] | None  # (surface, jieba flag)


def _is_verb(n: Neighbour) -> bool:
    return n is not None and n[1].startswith("v")


def context_reading(word: str, prev: Neighbour, nxt: Neighbour) -> str | None:
    """Numeric pinyin for a standalone polyphone in context, or None."""
    if word == "得":
        if prev and (prev[1].startswith("v") or prev[1] in ("a", "ad")):
            return "de5"  # complement marker: 跑得很快, 好得很
        if _is_verb(nxt) and (prev is None or prev[1] in ("r", "nr")):
            return "dei3"  # must: 我得走了
        return None
    if word == "地":
        reduplicated = prev is not None and len(prev[0]) == 2 and prev[0][0] == prev[0][1]
        if prev and (reduplicated or prev[1] in ("a", "ad", "z", "d")) and _is_verb(nxt):
            return "de5"  # adverbial marker: 慢慢地走, 认真地学
        return None
    if word == "长":
        if prev and prev[0] in DEGREE:
            return "chang2"  # long: 很长, 太长
        return None
    if word == "还":
        if nxt and (nxt[0] in HUAN_OBJECTS or nxt[0].startswith("钱")):
            return "huan2"  # give back: 还你钱, 还给他
        return None
    if word == "重":
        if _is_verb(nxt) and not (prev and prev[0] in DEGREE):
            return "chong2"  # again: 重说, 重做
        return None
    return None
