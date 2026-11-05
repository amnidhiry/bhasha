"""Subtitles from the learner's own Jellyfin server (BHASHA_JELLYFIN_URL and
BHASHA_JELLYFIN_API_KEY, an API key from Dashboard → API Keys).

Uses Jellyfin's documented REST API (api.jellyfin.org):
  GET /Items?searchTerm=…&Recursive=true&IncludeItemTypes=Movie,Episode,Series
  GET /Shows/{seriesId}/Episodes                       (a series' episodes)
  GET /Items?ids={id}&Fields=MediaSources,MediaStreams (subtitle streams)
  GET /Videos/{id}/{mediaSourceId}/Subtitles/{index}/Stream.srt
The last one converts any text subtitle (SRT, ASS, VTT, embedded or external)
to SRT; image subtitles (PGS, VobSub) can't be converted and are not offered.
The key goes in the `Authorization: MediaBrowser Token="…"` header."""

import httpx

from app.config import get_settings
from app.importing import ImportProblem
from app.importing.draft import Draft
from app.importing.subtitles import MAX_UPLOAD, draft_from_subtitles
from app.importing.textutil import current
from app.packs import get_pack

# Tests swap this for an httpx.MockTransport.
transport: httpx.BaseTransport | None = None

_FIELDS = "MediaSources,MediaStreams,ProductionYear"


def configured() -> bool:
    s = get_settings()
    return bool(s.jellyfin_url.strip() and s.jellyfin_api_key.strip())


def _base() -> str:
    return get_settings().jellyfin_url.strip().rstrip("/")


def _client() -> httpx.Client:
    if not configured():
        raise ImportProblem("Jellyfin isn't set up: set BHASHA_JELLYFIN_URL and BHASHA_JELLYFIN_API_KEY.")
    key = get_settings().jellyfin_api_key.strip()
    return httpx.Client(
        base_url=_base(), transport=transport, timeout=httpx.Timeout(20.0, connect=5.0),
        headers={"Authorization": f'MediaBrowser Client="bhasha", Device="bhasha", DeviceId="bhasha", '
                                  f'Version="0.1.0", Token="{key}"', "Accept": "application/json"},
    )


def _get(path: str, params: dict | None = None) -> httpx.Response:
    try:
        with _client() as c:
            r = c.get(path, params=params)
    except httpx.HTTPError as e:
        raise ImportProblem(f"Can't reach Jellyfin: {e}") from e
    if r.status_code in (401, 403):
        raise ImportProblem("Jellyfin refused the API key.")
    if r.status_code == 404:
        raise ImportProblem("Jellyfin doesn't have that item.")
    if r.status_code >= 400:
        raise ImportProblem(f"Jellyfin answered {r.status_code}.")
    return r


def _label(item: dict) -> str:
    """Display name: "Series S01E02 · Episode" for episodes, "Movie (2019)" for films."""
    name = item.get("Name") or "Untitled"
    if item.get("Type") == "Episode":
        se = ""
        if item.get("ParentIndexNumber") is not None and item.get("IndexNumber") is not None:
            se = f" S{item['ParentIndexNumber']:02d}E{item['IndexNumber']:02d}"
        series = item.get("SeriesName")
        return f"{series}{se} · {name}" if series else name
    if item.get("ProductionYear"):
        return f"{name} ({item['ProductionYear']})"
    return name


def _is_target(stream: dict) -> bool:
    """Is this subtitle track in the language being imported? (Codes and title words
    come from the pack: zh matches chi, zho, zh-Hans… and titles saying 中文.)"""
    pack = get_pack(current())
    lang = (stream.get("Language") or "").lower()
    if lang in pack.subtitle_codes or (lang.split("-")[0] == pack.code):
        return True
    text = f"{stream.get('DisplayTitle') or ''} {stream.get('Title') or ''}".lower()
    return any(w in text for w in pack.subtitle_words)


def _subtitle_streams(item: dict) -> list[dict]:
    out = []
    for source in item.get("MediaSources") or [{"Id": item.get("Id"), "MediaStreams": item.get("MediaStreams")}]:
        for s in source.get("MediaStreams") or []:
            if s.get("Type") != "Subtitle":
                continue
            text_based = s.get("IsTextSubtitleStream")
            if text_based is None:
                text_based = (s.get("Codec") or "").lower() not in ("pgssub", "hdmv_pgs_subtitle", "dvdsub", "dvd_subtitle", "dvbsub")
            out.append({
                "index": s.get("Index"),
                "media_source_id": source.get("Id") or item.get("Id"),
                "language": s.get("Language"),
                "title": s.get("DisplayTitle") or s.get("Title") or s.get("Language") or f"Track {s.get('Index')}",
                "codec": s.get("Codec"),
                "external": bool(s.get("IsExternal")),
                "default": bool(s.get("IsDefault")),
                "target": _is_target(s),
                "text": bool(text_based),
            })
    # The target language first, then the default track, then file order.
    out.sort(key=lambda s: (not s["target"], not s["default"], s["index"] if s["index"] is not None else 999))
    return out


def _summary(item: dict) -> dict:
    d = {"id": item.get("Id"), "name": _label(item), "type": item.get("Type")}
    if item.get("Type") != "Series":
        subs = _subtitle_streams(item) if (item.get("MediaSources") or item.get("MediaStreams")) else None
        d["target_subtitles"] = None if subs is None else sum(1 for s in subs if s["target"] and s["text"])
    return d


def search(query: str, limit: int = 20) -> list[dict]:
    r = _get("/Items", {
        "searchTerm": query, "Recursive": "true", "IncludeItemTypes": "Movie,Episode,Series",
        "Limit": str(limit), "Fields": _FIELDS,
    })
    return [_summary(i) for i in r.json().get("Items", [])]


def episodes(series_id: str) -> list[dict]:
    r = _get(f"/Shows/{series_id}/Episodes", {"Fields": _FIELDS})
    return [_summary(i) for i in r.json().get("Items", [])]


def _item(item_id: str) -> dict:
    items = _get("/Items", {"ids": item_id, "Fields": _FIELDS}).json().get("Items", [])
    if not items:
        raise ImportProblem("Jellyfin doesn't have that item.")
    return items[0]


def subtitles(item_id: str) -> dict:
    item = _item(item_id)
    return {"id": item.get("Id"), "name": _label(item), "subtitles": _subtitle_streams(item)}


def draft_from_jellyfin(item_id: str, index: int, media_source_id: str | None = None, title: str = "") -> Draft:
    item = _item(item_id)
    streams = _subtitle_streams(item)
    stream = next((s for s in streams if s["index"] == index and
                   (media_source_id is None or s["media_source_id"] == media_source_id)), None)
    if stream is None:
        raise ImportProblem("That item has no such subtitle track.")
    if not stream["text"]:
        raise ImportProblem("That track is image-based (PGS/VobSub) and can't be read as text.")
    path = f"/Videos/{item['Id']}/{stream['media_source_id']}/Subtitles/{index}/Stream.srt"
    data = _get(path).content
    if len(data) > MAX_UPLOAD:
        raise ImportProblem("That subtitle track is over 5 MB.")
    return draft_from_subtitles(
        data, title or _label(item), kind="jellyfin",
        source_url=f"{_base()}/web/#/details?id={item['Id']}",
        meta={"jellyfin": {"item_id": item["Id"], "media_source_id": stream["media_source_id"], "index": index,
                           "track": stream["title"]}},
    )
