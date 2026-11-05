"""Importer: links (through a MockTransport), EPUB, subtitles, Jellyfin, preview
coverage without writes, and saving parts."""

import io
import zipfile

import httpx
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.importing import ImportProblem, jellyfin, web
from app.importing.subtitles import subtitle_lines
from app.importing.textutil import html_to_text, split_parts
from app.models import Text, Unit

SENT = "我在银行工作。"  # 我 在 工作 known after the HSK 1 mark; 银行 not.


def _know_hsk1(client):
    client.post("/api/units/mark", json={"status": "known", "level_tag": "hsk3-2025:1"})


# --- links -----------------------------------------------------------------

ARTICLE = f"""<!doctype html><html><head><meta charset="utf-8"><title>我的工作 - 示例网</title>
<meta property="og:title" content="我的工作"></head>
<body><nav><a href="/">首页</a> <a href="/n">新闻</a></nav>
<article><h1>我的工作</h1>
<p>{SENT * 6}</p><p>{"我的朋友在医院工作。" * 6}</p><p>{"我的朋友是医生。" * 5}</p>
</article><footer>版权所有 © 示例网</footer></body></html>"""


@pytest.fixture()
def site(monkeypatch):
    """example.cn → a public address; pages served by a MockTransport."""
    pages = {
        "/article": (200, {"content-type": "text/html; charset=utf-8"}, ARTICLE.encode()),
        "/moved": (301, {"location": "/article"}, b""),
        "/to-local": (302, {"location": "http://127.0.0.1/admin"}, b""),
        "/big": (200, {"content-type": "text/html"}, b"<p>" + "我".encode() * 800_000 + b"</p>"),
        "/pdf": (200, {"content-type": "application/pdf"}, b"%PDF-1.4"),
    }
    seen = []

    def handler(req: httpx.Request):
        seen.append(str(req.url))
        status, headers, body = pages.get(req.url.path, (404, {}, b""))
        return httpx.Response(status, headers=headers, content=body)

    real_resolve = web.resolve
    monkeypatch.setattr(web, "resolve", lambda h: ["93.184.216.34"] if h == "example.cn" else real_resolve(h))
    monkeypatch.setattr(web, "transport", httpx.MockTransport(handler))
    return seen


def test_url_preview_extracts_article_and_writes_nothing(client, site):
    _know_hsk1(client)
    with client.session_factory() as s:
        units_before = s.scalar(select(func.count()).select_from(Unit))
    r = client.post("/api/import/url/preview", json={"url": "https://example.cn/moved"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["title"] == "我的工作"
    assert p["source_url"] == "https://example.cn/article"
    body = p["parts"][0]["body"]
    assert SENT in body and "版权所有" not in body and "首页" not in body
    assert p["characters"] > 100
    assert 0 < p["coverage"] < 1
    with client.session_factory() as s:
        assert s.scalar(select(func.count()).select_from(Unit)) == units_before
        assert s.scalar(select(func.count()).select_from(Text)) == 0

    saved = client.post("/api/import/texts", json={
        "kind": "url", "source_url": p["source_url"], "parts": [{"title": p["title"], "body": body}]}).json()
    t = client.get(f"/api/texts/{saved['texts'][0]['id']}").json()
    assert t["provenance"] == "imported" and t["source_url"] == "https://example.cn/article"
    assert t["meta"]["import"]["kind"] == "url"
    # Preview coverage is what the saved text records.
    assert t["coverage_at_creation"] == pytest.approx(p["coverage"])


@pytest.mark.parametrize("url, needle", [
    ("ftp://example.cn/x", "http"),
    ("http://127.0.0.1/", "private or local"),
    ("http://169.254.169.254/latest/meta-data", "private or local"),
    ("http://[::1]:8000/", "private or local"),
    ("http://10.0.0.5/", "private or local"),
    ("https://example.cn/to-local", "private or local"),  # redirect target re-checked
    ("https://example.cn/big", "2 MB"),
    ("https://example.cn/pdf", "not a web page"),
    ("https://example.cn/missing", "404"),
])
def test_url_guards(client, site, url, needle):
    r = client.post("/api/import/url/preview", json={"url": url})
    assert r.status_code == 422
    assert needle in r.json()["detail"]
    assert not any("127.0.0.1" in u for u in site)


def test_allowlist_lets_lan_hosts_through(client, monkeypatch):
    monkeypatch.setattr(web, "transport", httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-type": "text/html"}, content=ARTICLE.encode())))
    monkeypatch.setattr(web, "resolve", lambda h: ["192.168.1.20"])
    with pytest.raises(ImportProblem):
        web.check_url("http://wiki.lan/a")
    monkeypatch.setattr(get_settings(), "import_allow_hosts", "wiki.lan")
    web.check_url("http://wiki.lan/a")
    monkeypatch.setattr(get_settings(), "import_allow_hosts", "192.168.1.0/24")
    assert client.post("/api/import/url/preview", json={"url": "http://nas.lan/a"}).status_code == 200


# --- EPUB ------------------------------------------------------------------

def _epub(nav: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>""")
        z.writestr("OEBPS/content.opf", f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>小故事</dc:title><dc:creator>王老师</dc:creator></metadata>
<manifest>
 <item id="cover" href="cover.xhtml" media-type="application/xhtml+xml"/>
 {'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>' if nav else ''}
 <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
 <item id="c1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
 <item id="c2" href="text/ch%202.xhtml" media-type="application/xhtml+xml"/>
 <item id="css" href="style.css" media-type="text/css"/>
</manifest>
<spine toc="ncx"><itemref idref="cover"/><itemref idref="c1"/><itemref idref="c2"/></spine></package>""")
        z.writestr("OEBPS/cover.xhtml", "<html><body><img src='cover.jpg'/></body></html>")
        z.writestr("OEBPS/nav.xhtml", """<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body><nav epub:type="toc"><ol><li><a href="text/ch1.xhtml">第一章 银行</a></li>
<li><a href="text/ch%202.xhtml#start">第二章 朋友</a></li></ol></nav></body></html>""")
        z.writestr("OEBPS/toc.ncx", """<?xml version="1.0"?><ncx xmlns="http://www.daisy.org/z3986/2005/ncx/"><navMap>
<navPoint id="n1"><navLabel><text>NCX 一</text></navLabel><content src="text/ch1.xhtml"/></navPoint>
<navPoint id="n2"><navLabel><text>NCX 二</text></navLabel><content src="text/ch%202.xhtml"/></navPoint>
</navMap></ncx>""")
        z.writestr("OEBPS/text/ch1.xhtml", f"""<html xmlns="http://www.w3.org/1999/xhtml"><head><title>x</title>
<style>p {{ color: red }}</style></head><body><h1>第一章 银行</h1>
<p><ruby>我<rt>wǒ</rt></ruby><ruby>在<rp>(</rp><rt>zài</rt><rp>)</rp></ruby>银行工作。</p>
<p>{SENT}</p></body></html>""")
        z.writestr("OEBPS/text/ch 2.xhtml", "<html><body><h2>第二章</h2><p>我的朋友是医生。</p></body></html>")
    return buf.getvalue()


def test_epub_chapters_titles_and_ruby(client):
    r = client.post("/api/import/epub/chapters", files={"file": ("book.epub", _epub(), "application/epub+zip")})
    assert r.status_code == 200, r.text
    book = r.json()
    assert book["title"] == "小故事" and book["author"] == "王老师"
    assert [c["title"] for c in book["chapters"]] == ["第一章 银行", "第二章 朋友"]  # cover skipped

    p = client.post("/api/import/epub/preview", files={"file": ("book.epub", _epub())}, data={"start": "0"}).json()
    body = p["parts"][0]["body"]
    assert body.startswith("我在银行工作。") and "wǒ" not in body and "zài" not in body and "(" not in body
    assert "color" not in body
    assert p["title"] == "小故事 · 第一章 银行"

    both = client.post("/api/import/epub/preview", files={"file": ("book.epub", _epub())},
                       data={"start": "0", "end": "1"}).json()
    assert "医生" in both["parts"][0]["body"] and both["meta"]["chapters"] == [0, 1]
    assert client.post("/api/import/epub/preview", files={"file": ("b.epub", _epub())},
                       data={"start": "5"}).status_code == 422


def test_epub_ncx_fallback_and_bad_files(client):
    book = client.post("/api/import/epub/chapters", files={"file": ("b.epub", _epub(nav=False))}).json()
    assert [c["title"] for c in book["chapters"]] == ["NCX 一", "NCX 二"]
    r = client.post("/api/import/epub/chapters", files={"file": ("b.epub", b"not a zip")})
    assert r.status_code == 422 and "EPUB" in r.json()["detail"]


def test_html_to_text_blocks():
    text, heads = html_to_text("<div>一<br/>二</div><p>三\n四</p><script>var x='五'</script>")
    assert text == "一\n二\n三 四" and heads == []


# --- subtitles ---------------------------------------------------------------

BILINGUAL_SRT = """1
00:00:01,000 --> 00:00:03,000
<i>我在银行工作。</i>
I work at a bank.

2
00:00:03,500 --> 00:00:05,000
{\\an8}你好 朋友
Hello, friend.

3
00:00:05,500 --> 00:00:06,000
你好 朋友
Hello, friend.

4
00:00:06,000 --> 00:00:07,000
我想，
I think,

5
00:00:07,000 --> 00:00:08,000
他是医生。
he is a doctor.
"""

VTT = """WEBVTT
Kind: captions

NOTE a comment 我不要

00:01.000 --> 00:02.000 align:start
<v 小明><c.yellow>我在</c>银行工作。</v>

intro
00:02.500 --> 00:04.000
- 你是医生吗？
- 是的。
"""


def test_subtitle_cleaning_bilingual_merge_and_dedupe():
    lines, bilingual = subtitle_lines(BILINGUAL_SRT.encode("utf-8-sig"))
    assert bilingual
    assert lines == ["我在银行工作。", "你好，朋友", "我想，他是医生。"]
    vtt, bi = subtitle_lines(VTT.encode())
    assert not bi and vtt == ["我在银行工作。", "你是医生吗？是的。"]
    gbk, _ = subtitle_lines(BILINGUAL_SRT.encode("gbk"))
    assert gbk == lines


def test_subtitles_preview_and_split_into_parts(client):
    _know_hsk1(client)
    r = client.post("/api/import/subtitles/preview",
                    files={"file": ("Bank_Show.S01E01.srt", BILINGUAL_SRT.encode(), "application/x-subrip")})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["title"] == "Bank Show S01E01" and len(p["parts"]) == 1
    assert p["warnings"] and p["meta"]["bilingual"]

    cues = "\n".join(f"{i}\n00:00:{i % 60:02d},000 --> 00:00:{i % 60:02d},500\n第{i}句：我在银行工作。\n"
                     for i in range(1, 501))
    long = client.post("/api/import/subtitles/preview", files={"file": ("x.srt", cues.encode())},
                       data={"title": "银行"}).json()
    n = len(long["parts"])
    assert n > 1 and long["parts"][0]["title"] == f"银行 (1/{n})" and long["parts"][-1]["title"] == f"银行 ({n}/{n})"
    assert all(900 < part["characters"] < 2100 for part in long["parts"])
    assert sum(part["characters"] for part in long["parts"]) == long["characters"]

    saved = client.post("/api/import/texts", json={
        "kind": "subtitles", "parts": [{"title": q["title"], "body": q["body"]} for q in long["parts"]]}).json()
    ids = [t["id"] for t in saved["texts"]]
    metas = [client.get(f"/api/texts/{i}").json()["meta"]["import"] for i in ids]
    assert [m["part"] for m in metas] == list(range(1, n + 1)) and {m["group"] for m in metas} == {ids[0]}

    bad = client.post("/api/import/subtitles/preview", files={"file": ("x.srt", b"1\n00:00:01,000 --> 00:00:02,000\nHello\n")})
    assert bad.status_code == 422


def test_split_parts_folds_short_tail():
    parts = split_parts(["一" * 700, "二" * 700, "三" * 700, "四" * 100], target=1500)
    assert len(parts) == 2 and parts[1].endswith("四" * 100)


# --- Jellyfin ----------------------------------------------------------------

ITEM = {
    "Id": "ep1", "Name": "银行", "Type": "Episode", "SeriesName": "我的工作", "ParentIndexNumber": 1, "IndexNumber": 2,
    "MediaSources": [{"Id": "src1", "MediaStreams": [
        {"Type": "Video", "Index": 0},
        {"Type": "Subtitle", "Index": 2, "Language": "eng", "DisplayTitle": "English - SUBRIP", "Codec": "subrip",
         "IsTextSubtitleStream": True, "IsDefault": True},
        {"Type": "Subtitle", "Index": 3, "Language": "chi", "DisplayTitle": "Chinese Simplified - PGSSUB",
         "Codec": "PGSSUB", "IsTextSubtitleStream": False},
        {"Type": "Subtitle", "Index": 4, "Language": "chi", "DisplayTitle": "简体中文 - ASS", "Codec": "ass",
         "IsTextSubtitleStream": True, "IsExternal": True},
    ]}],
}


@pytest.fixture()
def jf(monkeypatch):
    monkeypatch.setattr(get_settings(), "jellyfin_url", "http://jellyfin.lan:8096/")
    monkeypatch.setattr(get_settings(), "jellyfin_api_key", "k123")
    calls = []

    def handler(req: httpx.Request):
        calls.append(req)
        assert 'Token="k123"' in req.headers["authorization"]
        path, q = req.url.path, req.url.params
        if path == "/Items" and q.get("searchTerm"):
            return httpx.Response(200, json={"Items": [
                ITEM, {"Id": "s1", "Name": "我的工作", "Type": "Series"},
                {"Id": "m1", "Name": "电影", "Type": "Movie", "ProductionYear": 2019, "MediaStreams": []}]})
        if path == "/Items" and q.get("ids") == "ep1":
            return httpx.Response(200, json={"Items": [ITEM]})
        if path == "/Items":
            return httpx.Response(200, json={"Items": []})
        if path == "/Shows/s1/Episodes":
            return httpx.Response(200, json={"Items": [ITEM]})
        if path == "/Videos/ep1/src1/Subtitles/4/Stream.srt":
            return httpx.Response(200, content=BILINGUAL_SRT.encode())
        return httpx.Response(404)

    monkeypatch.setattr(jellyfin, "transport", httpx.MockTransport(handler))
    return calls


def test_jellyfin_config_hidden_until_set(client):
    assert client.get("/api/import/config").json()["jellyfin"] is False
    assert client.get("/api/import/jellyfin/search", params={"q": "x"}).status_code == 422


def test_jellyfin_search_subtitles_and_preview(client, jf):
    assert client.get("/api/import/config").json()["jellyfin"] is True
    found = client.get("/api/import/jellyfin/search", params={"q": "银行"}).json()
    assert found[0] == {"id": "ep1", "name": "我的工作 S01E02 · 银行", "type": "Episode", "chinese_subtitles": 1}
    assert found[1]["type"] == "Series" and found[2]["name"] == "电影 (2019)"
    assert client.get("/api/import/jellyfin/series/s1/episodes").json()[0]["id"] == "ep1"

    subs = client.get("/api/import/jellyfin/items/ep1/subtitles").json()["subtitles"]
    assert [s["index"] for s in subs] == [3, 4, 2]  # Chinese first
    assert subs[0]["text"] is False and subs[1]["text"] is True

    image = client.post("/api/import/jellyfin/preview", json={"item_id": "ep1", "index": 3})
    assert image.status_code == 422 and "image" in image.json()["detail"]
    p = client.post("/api/import/jellyfin/preview", json={"item_id": "ep1", "index": 4, "media_source_id": "src1"}).json()
    assert p["kind"] == "jellyfin" and p["title"] == "我的工作 S01E02 · 银行"
    assert p["parts"][0]["body"].startswith("我在银行工作。")
    assert p["source_url"] == "http://jellyfin.lan:8096/web/#/details?id=ep1"
    assert any(c.url.path == "/Videos/ep1/src1/Subtitles/4/Stream.srt" for c in jf)

    assert client.post("/api/import/jellyfin/preview", json={"item_id": "nope", "index": 4}).status_code == 422
