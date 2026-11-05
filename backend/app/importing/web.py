"""Link import: fetch a page server-side and keep the article text.

Extraction uses trafilatura. It is actively maintained, scores at or near the
top of the open benchmarks for main-text extraction, handles non-English pages
well (readability-lxml's scoring leans on English text density and comma
counts, which Chinese pages defeat), returns the title from page metadata, and
decodes GBK/GB2312 pages from their bytes. Its dependencies are lxml plus a
few small pure-Python packages. We fetch with httpx ourselves rather than with
trafilatura's downloader so the SSRF checks below apply to every hop.

SSRF: http(s) only, a size cap, a timeout, redirects followed by hand with the
target re-checked each hop, and no loopback, private, link-local or other
non-global address unless the host is in BHASHA_IMPORT_ALLOW_HOSTS. (A DNS
answer that changes between our check and httpx's connect could still slip
through; for a single-user homelab app that residual risk is accepted.)"""

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import httpx
import trafilatura

from app.config import get_settings
from app.importing import ImportProblem
from app.importing.draft import MAX_BODY, Draft, Part
from app.importing.textutil import decode, han_count, han_ratio, tidy

# Tests swap this for an httpx.MockTransport.
transport: httpx.BaseTransport | None = None

MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = httpx.Timeout(15.0, connect=5.0)
MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (compatible; bhasha-importer/0.1; self-hosted reader)"


def resolve(host: str) -> list[str]:
    """Addresses a host name resolves to. Tests replace this (no DNS in CI)."""
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ImportProblem(f"Can't find the site {host!r}.") from e
    return sorted({i[4][0] for i in infos})


def _allowlist() -> tuple[set[str], list[ipaddress._BaseNetwork]]:
    names, nets = set(), []
    for item in get_settings().import_allow_hosts.split(","):
        item = item.strip().lower()
        if not item:
            continue
        try:
            nets.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            names.add(item.rstrip("."))
    return names, nets


def check_url(url: str) -> None:
    """Raise ImportProblem unless the URL is http(s) to a public address, or to
    a host the allowlist names."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ImportProblem("Only http and https links can be imported.")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise ImportProblem("That link has no host name.")
    names, nets = _allowlist()
    if host in names:
        return
    for addr in resolve(host):
        ip = ipaddress.ip_address(addr.split("%")[0])
        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
        if any(ip in n for n in nets):
            continue
        if not ip.is_global or ip.is_multicast:
            raise ImportProblem(
                f"{host} points to a private or local address ({ip}). "
                "Add it to BHASHA_IMPORT_ALLOW_HOSTS to import from your own network."
            )


def fetch(url: str) -> tuple[str, bytes, str]:
    """(final URL, body bytes, content type), at most MAX_BYTES."""
    with httpx.Client(timeout=TIMEOUT, transport=transport, follow_redirects=False,
                      headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                               "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.5"}) as c:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url)
            try:
                with c.stream("GET", url) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            raise ImportProblem("The site sent a redirect with no address.")
                        url = urljoin(url, loc)
                        continue
                    if r.status_code >= 400:
                        raise ImportProblem(f"The site answered {r.status_code}.")
                    declared = r.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                        raise ImportProblem("That page is over 2 MB; try the article's own link or paste it.")
                    buf = bytearray()
                    for chunk in r.iter_bytes():
                        buf += chunk
                        if len(buf) > MAX_BYTES:
                            raise ImportProblem("That page is over 2 MB; try the article's own link or paste it.")
                    return str(r.url), bytes(buf), r.headers.get("content-type", "")
            except httpx.TimeoutException as e:
                raise ImportProblem("The site took too long to answer.") from e
            except httpx.HTTPError as e:
                raise ImportProblem(f"Couldn't fetch the page: {e}") from e
    raise ImportProblem("Too many redirects.")


def extract(html: bytes, url: str) -> tuple[str, str]:
    """(title, article text) of an HTML page."""
    doc = trafilatura.bare_extraction(html, url=url, with_metadata=True, include_comments=False,
                                      include_tables=False, favor_precision=True)
    text = tidy(doc.text or "") if doc is not None else ""
    if han_count(text) < 20:
        # Precision mode can drop short pages entirely; try the default balance.
        doc = trafilatura.bare_extraction(html, url=url, with_metadata=True, include_comments=False)
        text = tidy(doc.text or "") if doc is not None else ""
    title = ((doc.title if doc is not None else "") or "").strip()
    # The headline often opens the body too.
    lines = text.split("\n")
    if title and lines and lines[0].strip() == title:
        text = "\n".join(lines[1:]).strip()
    return title, text


def draft_from_url(url: str) -> Draft:
    url = url.strip()
    final_url, data, ctype = fetch(url)
    ctype = ctype.split(";")[0].strip().lower()
    if ctype == "text/plain":
        title, text = "", tidy(decode(data))
    elif ctype and "html" not in ctype and "xml" not in ctype:
        raise ImportProblem(f"That link is {ctype}, not a web page.")
    else:
        title, text = extract(data, final_url)
    if han_count(text) == 0:
        raise ImportProblem("Couldn't find any Chinese text on that page.")
    if len(text) > MAX_BODY:
        text = text[:MAX_BODY].rsplit("\n", 1)[0]
    warnings = []
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if lines and sum(han_ratio(ln) >= 0.5 for ln in lines) < len(lines) / 2:
        warnings.append("Much of this page isn't Chinese.")
    title = title or urlsplit(final_url).hostname or "Web page"
    return Draft(kind="url", title=title[:256], parts=[Part(title[:256], text)], source_url=final_url[:1024])
