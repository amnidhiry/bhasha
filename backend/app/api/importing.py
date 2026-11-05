"""Importer API. Each source has a preview that scores the text against what you
know without saving anything; POST /import/texts then saves the previewed parts.

  GET  /import/config                    which sources are available
  POST /import/url/preview               {url}
  POST /import/epub/chapters             multipart file
  POST /import/epub/preview              multipart file, start, end
  POST /import/subtitles/preview         multipart file, title
  GET  /import/jellyfin/search?q=
  GET  /import/jellyfin/series/{id}/episodes
  GET  /import/jellyfin/items/{id}/subtitles
  POST /import/jellyfin/preview          {item_id, index, media_source_id}
  POST /import/texts                     {kind, parts, source_url, meta}"""

from pathlib import PurePath

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_language, current_user
from app.db import get_db
from app.importing import ImportProblem, epub, jellyfin, subtitles, web
from app.importing.draft import MAX_BODY, preview
from app.importing.textutil import importing_language
from app.jobs import enqueue_render
from app.models import AppUser
from app.packs import INSTALLED
from app.reader import create_text

router = APIRouter(prefix="/import", tags=["import"])


def _problem(e: ImportProblem) -> HTTPException:
    return HTTPException(422, str(e))


async def _upload(file: UploadFile, cap: int, what: str) -> bytes:
    data = await file.read(cap + 1)
    if len(data) > cap:
        raise HTTPException(413, f"That {what} is over {cap // (1024 * 1024)} MB.")
    if not data:
        raise HTTPException(422, "That file is empty.")
    return data


def _stem(filename: str | None) -> str:
    stem = PurePath(filename or "").stem
    # "Movie.2019.1080p.zh" → "Movie 2019 1080p zh"; the learner can rename it.
    return stem.replace("_", " ").replace(".", " ").strip()


@router.get("/config")
def import_config():
    return {
        "sources": ["paste", "url", "epub", "subtitles"] + (["jellyfin"] if jellyfin.configured() else []),
        "jellyfin": jellyfin.configured(),
        "max_url_bytes": web.MAX_BYTES,
        "max_epub_bytes": epub.MAX_UPLOAD,
        "max_subtitle_bytes": subtitles.MAX_UPLOAD,
        "part_characters": subtitles.PART_CHARS,
    }


class UrlIn(BaseModel):
    url: str = Field(min_length=4, max_length=1024)


@router.post("/url/preview")
def url_preview(body: UrlIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user), lang: str = Depends(current_language)):
    with importing_language(lang):
        try:
            draft = web.draft_from_url(body.url)
        except ImportProblem as e:
            raise _problem(e)
        return preview(db, user.id, draft)


@router.post("/epub/chapters")
async def epub_chapters(file: UploadFile = File(...), lang: str = Depends(current_language)):
    data = await _upload(file, epub.MAX_UPLOAD, "book")
    with importing_language(lang):
        try:
            return epub.chapter_list(epub.read_book(data))
        except ImportProblem as e:
            raise _problem(e)


@router.post("/epub/preview")
async def epub_preview(file: UploadFile = File(...), start: int = Form(0), end: int | None = Form(None),
                       db: Session = Depends(get_db), user: AppUser = Depends(current_user), lang: str = Depends(current_language)):
    data = await _upload(file, epub.MAX_UPLOAD, "book")
    with importing_language(lang):
        try:
            draft = epub.draft_from_book(epub.read_book(data), start, end)
        except ImportProblem as e:
            raise _problem(e)
        return preview(db, user.id, draft)


@router.post("/subtitles/preview")
async def subtitles_preview(file: UploadFile = File(...), title: str = Form(""),
                            db: Session = Depends(get_db), user: AppUser = Depends(current_user), lang: str = Depends(current_language)):
    data = await _upload(file, subtitles.MAX_UPLOAD, "subtitle file")
    with importing_language(lang):
        try:
            draft = subtitles.draft_from_subtitles(data, title or _stem(file.filename))
        except ImportProblem as e:
            raise _problem(e)
        return preview(db, user.id, draft)


@router.get("/jellyfin/search")
def jellyfin_search(q: str, lang: str = Depends(current_language)):
    if not q.strip():
        return []
    with importing_language(lang):
        try:
            return jellyfin.search(q.strip())
        except ImportProblem as e:
            raise _problem(e)


@router.get("/jellyfin/series/{series_id}/episodes")
def jellyfin_episodes(series_id: str, lang: str = Depends(current_language)):
    with importing_language(lang):
        try:
            return jellyfin.episodes(series_id)
        except ImportProblem as e:
            raise _problem(e)


@router.get("/jellyfin/items/{item_id}/subtitles")
def jellyfin_subtitles(item_id: str, lang: str = Depends(current_language)):
    with importing_language(lang):
        try:
            return jellyfin.subtitles(item_id)
        except ImportProblem as e:
            raise _problem(e)


class JellyfinIn(BaseModel):
    item_id: str = Field(max_length=64)
    index: int
    media_source_id: str | None = Field(default=None, max_length=64)
    title: str = Field(default="", max_length=240)


@router.post("/jellyfin/preview")
def jellyfin_preview(body: JellyfinIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user), lang: str = Depends(current_language)):
    with importing_language(lang):
        try:
            draft = jellyfin.draft_from_jellyfin(body.item_id, body.index, body.media_source_id, body.title)
        except ImportProblem as e:
            raise _problem(e)
        return preview(db, user.id, draft)


class PartIn(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=MAX_BODY)


class SaveIn(BaseModel):
    kind: str = Field(default="paste", max_length=32)
    parts: list[PartIn] = Field(min_length=1, max_length=100)
    source_url: str | None = Field(default=None, max_length=1024)
    meta: dict = Field(default_factory=dict)
    language: str | None = None  # the active language when omitted


@router.post("/texts")
def save_texts(body: SaveIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user), lang: str = Depends(current_language)):
    """Save previewed parts as texts (provenance "imported"); a multi-part import
    links its parts through meta.import.group (the first part's id)."""
    language = body.language or lang
    if language not in INSTALLED:
        raise HTTPException(400, f"no language pack for {language!r}")
    out, group = [], None
    for i, p in enumerate(body.parts, 1):
        text = create_text(db, user.id, language, p.title, p.body, "imported", body.source_url)
        group = group or text.id
        text.meta = {**(text.meta or {}), "import": {
            **{k: v for k, v in body.meta.items() if k not in ("group", "part", "of")},
            "kind": body.kind, "part": i, "of": len(body.parts), "group": group,
        }}
        db.commit()
        enqueue_render(db, user.id, text.id)
        out.append({"id": text.id, "title": text.title, "coverage_at_creation": text.coverage_at_creation})
    return {"texts": out}
