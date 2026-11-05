"""EPUB import with the standard library: zipfile for the container, ElementTree
for the package (OPF), NCX and nav documents, and our HTML-to-text pass for the
chapters, which drops ruby (pinyin/zhuyin) annotations.

Chapters follow the spine; titles come from the table of contents (EPUB 3 nav,
else EPUB 2 NCX), then the chapter's first heading, then "Chapter N"."""

import io
import posixpath
import zipfile
from dataclasses import dataclass
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from app.importing import ImportProblem
from app.importing.draft import MAX_BODY, Draft, Part
from app.importing.textutil import han_count, html_to_text

MAX_UPLOAD = 50 * 1024 * 1024
MAX_MEMBER = 20 * 1024 * 1024  # uncompressed, per file: refuses zip bombs
_HTML_TYPES = {"application/xhtml+xml", "text/html", "application/x-dtbook+xml"}


@dataclass
class Chapter:
    index: int  # position among readable chapters, as the PWA sends it back
    title: str
    href: str
    text: str


@dataclass
class Book:
    title: str
    author: str | None
    chapters: list[Chapter]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_all(root: ET.Element, name: str):
    return (e for e in root.iter() if _local(e.tag) == name)


def _read(z: zipfile.ZipFile, name: str) -> bytes:
    try:
        info = z.getinfo(name)
    except KeyError as e:
        raise ImportProblem(f"The book is missing {name}.") from e
    if info.file_size > MAX_MEMBER:
        raise ImportProblem("A file inside that book is too large.")
    return z.read(info)


def _xml(data: bytes) -> ET.Element:
    # Python's expat refuses entity-expansion bombs and never fetches external entities.
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise ImportProblem("The book's package file is damaged.") from e


def _join(base_dir: str, href: str) -> str:
    return posixpath.normpath(posixpath.join(base_dir, unquote(href.split("#", 1)[0])))


def _toc_titles(z: zipfile.ZipFile, opf_dir: str, manifest: dict, spine_toc: str | None) -> dict[str, str]:
    """Zip path → first TOC title pointing at it."""
    titles: dict[str, str] = {}
    nav = next((m for m in manifest.values() if "nav" in m["properties"].split()), None)
    if nav:
        try:
            root = _xml(_read(z, nav["path"]))
            base = posixpath.dirname(nav["path"])
            navs = [n for n in _find_all(root, "nav")
                    if any(_local(k) == "type" and "toc" in v.split() for k, v in n.attrib.items())]
            for n in navs or list(_find_all(root, "nav"))[:1]:
                for a in _find_all(n, "a"):
                    label = " ".join("".join(a.itertext()).split())
                    href = a.get("href")
                    if label and href:
                        titles.setdefault(_join(base, href), label)
        except ImportProblem:
            pass
    ncx = manifest.get(spine_toc or "") or next(
        (m for m in manifest.values() if m["media_type"] == "application/x-dtbncx+xml"), None)
    if ncx and not titles:
        try:
            root = _xml(_read(z, ncx["path"]))
            base = posixpath.dirname(ncx["path"])
            for point in _find_all(root, "navPoint"):
                label = next((" ".join("".join(t.itertext()).split()) for t in _find_all(point, "text")), "")
                content = next(_find_all(point, "content"), None)
                if label and content is not None and content.get("src"):
                    titles.setdefault(_join(base, content.get("src")), label)
        except ImportProblem:
            pass
    return titles


def read_book(data: bytes) -> Book:
    if len(data) > MAX_UPLOAD:
        raise ImportProblem("That book is over 50 MB.")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise ImportProblem("That isn't an EPUB file (not a zip archive).") from e
    with z:
        container = _xml(_read(z, "META-INF/container.xml"))
        rootfile = next((e.get("full-path") for e in _find_all(container, "rootfile") if e.get("full-path")), None)
        if not rootfile:
            raise ImportProblem("The book doesn't say where its contents are.")
        opf = _xml(_read(z, rootfile))
        opf_dir = posixpath.dirname(rootfile)

        title = next((" ".join("".join(e.itertext()).split()) for e in _find_all(opf, "title")), "") or "Book"
        author = next((" ".join("".join(e.itertext()).split()) for e in _find_all(opf, "creator")), None) or None
        manifest = {}
        for item in _find_all(opf, "item"):
            if item.get("id") and item.get("href"):
                manifest[item.get("id")] = {
                    "path": _join(opf_dir, item.get("href")),
                    "media_type": item.get("media-type", ""),
                    "properties": item.get("properties", ""),
                }
        spine = next(_find_all(opf, "spine"), None)
        if spine is None:
            raise ImportProblem("The book has no reading order (spine).")
        toc = _toc_titles(z, opf_dir, manifest, spine.get("toc"))

        chapters: list[Chapter] = []
        for ref in _find_all(spine, "itemref"):
            item = manifest.get(ref.get("idref", ""))
            if not item or item["media_type"] not in _HTML_TYPES or "nav" in item["properties"].split():
                continue
            try:
                raw = _read(z, item["path"])
            except ImportProblem:
                continue
            text, headings = html_to_text(raw.decode("utf-8", errors="replace"))
            if han_count(text) == 0:
                continue  # cover pages, image-only pages, English front matter
            ch_title = toc.get(item["path"]) or (headings[0] if headings else f"Chapter {len(chapters) + 1}")
            chapters.append(Chapter(len(chapters), ch_title[:200], item["path"], text))
    if not chapters:
        raise ImportProblem("Couldn't find any Chinese text in that book.")
    return Book(title[:200], author, chapters)


def chapter_list(book: Book) -> dict:
    return {
        "title": book.title,
        "author": book.author,
        "chapters": [
            {"index": c.index, "title": c.title, "characters": han_count(c.text), "excerpt": c.text[:60]}
            for c in book.chapters
        ],
    }


def draft_from_book(book: Book, start: int, end: int | None = None) -> Draft:
    end = start if end is None else end
    if not (0 <= start <= end < len(book.chapters)):
        raise ImportProblem("Pick chapters from the list.")
    picked = book.chapters[start:end + 1]
    if len(picked) == 1:
        body = picked[0].text
        # The chapter title usually opens the text too.
        first, _, rest = body.partition("\n")
        if first.strip() == picked[0].title and rest.strip():
            body = rest.strip()
        title = f"{book.title} · {picked[0].title}"
    else:
        body = "\n\n".join(c.text for c in picked)
        title = f"{book.title} · {picked[0].title} – {picked[-1].title}"
    if len(body) > MAX_BODY:
        raise ImportProblem("That's too much for one text; pick fewer chapters.")
    title = title[:256]
    return Draft(kind="epub", title=title, parts=[Part(title, body)],
                 meta={"book": book.title, "author": book.author, "chapters": [start, end],
                       "chapter_titles": [c.title for c in picked]})
