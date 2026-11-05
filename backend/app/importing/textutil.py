"""Small text helpers shared by the importers: Han counting, decoding, a
stdlib HTML-to-text pass and splitting long text into parts."""

import re
from html.parser import HTMLParser

_HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0003134f]")
_LATIN_WORD = re.compile(r"[A-Za-zÀ-ɏ]+")


def han_count(s: str) -> int:
    return len(_HAN.findall(s))


def han_ratio(line: str) -> float:
    """Han characters against Han characters plus Latin words: 我用iPhone is
    Chinese (2 of 3), "Hello world" is not. Lines with neither score 0."""
    han = han_count(line)
    latin = len(_LATIN_WORD.findall(line))
    return han / (han + latin) if han + latin else 0.0


def decode(data: bytes) -> str:
    """Subtitle and plain-text files: UTF-8 (with or without BOM), UTF-16 with
    BOM, then GB18030, which covers the GBK/GB2312 files Chinese sites serve."""
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    for enc in ("utf-8-sig", "gb18030", "big5"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def tidy(text: str) -> str:
    """Collapse runs of spaces, trim lines, keep at most one blank line."""
    lines = [re.sub(r"[ \t　\xa0]+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


_BLOCK = {
    "p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote", "section",
    "article", "header", "footer", "dt", "dd", "pre", "hr", "table", "ul", "ol", "figure", "figcaption",
}
# Ruby annotations (pinyin or zhuyin above the characters) and things that are never text.
_SKIP = {"rt", "rp", "rtc", "script", "style", "head", "title", "svg", "math", "noscript", "template"}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.headings: list[str] = []
        self._heading: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip += 1
        elif tag in _BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3") and self._heading is None and not self.skip:
            self._heading = []

    def handle_startendtag(self, tag, attrs):
        if tag in ("br", "hr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK:
            self.parts.append("\n")
        if tag in ("h1", "h2", "h3") and self._heading is not None:
            h = " ".join("".join(self._heading).split())
            if h:
                self.headings.append(h)
            self._heading = None

    def handle_data(self, data):
        if self.skip:
            return
        # Source line breaks inside a paragraph are formatting, not text.
        data = data.replace("\r", "").replace("\n", " ")
        self.parts.append(data)
        if self._heading is not None:
            self._heading.append(data)


def html_to_text(html: str) -> tuple[str, list[str]]:
    """Visible text of an (X)HTML document with one line per block, ruby
    annotations dropped, plus its h1-h3 headings (a fallback chapter title)."""
    p = _TextParser()
    p.feed(html)
    p.close()
    lines = [ln for ln in tidy("".join(p.parts)).split("\n") if ln]
    return "\n".join(lines), p.headings


def split_parts(lines: list[str], target: int = 1500, min_last: int = 300) -> list[str]:
    """Group lines into parts of at most about `target` Han characters (a part
    goes over only when one line is that long), breaking only between lines.
    A short tail is folded into the previous part."""
    parts: list[list[str]] = [[]]
    count = 0
    for ln in lines:
        n = han_count(ln)
        if parts[-1] and count + n > target and count >= target // 2:
            parts.append([])
            count = 0
        parts[-1].append(ln)
        count += n
    if len(parts) > 1 and sum(han_count(ln) for ln in parts[-1]) < min_last:
        tail = parts.pop()
        parts[-1].extend(tail)
    return ["\n".join(p) for p in parts if p]
