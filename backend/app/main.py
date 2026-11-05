from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import jobs, llm, lookup, mine, progress, reviews, texts
from app.bootstrap import ensure_defaults, warm_packs
from app.config import get_settings
from app.db import SessionLocal


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_defaults(db)
        warm_packs(db)
    yield


app = FastAPI(title="bhasha", version="0.1.0", lifespan=lifespan, docs_url="/api/docs",
              openapi_url="/api/openapi.json")
for r in (reviews.router, texts.router, lookup.router, mine.router, progress.router, llm.router, jobs.router):
    app.include_router(r, prefix="/api")


@app.get("/health")
def health():
    return {"ok": True}


# The built PWA (web/dist) is served from the same origin, so no CORS and one container.
web_dir = Path(get_settings().web_dir)
if (web_dir / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (web_dir / path).resolve()
        if path and f.is_file() and web_dir.resolve() in f.parents:
            # The service worker must never be cached by the browser, or updates stall.
            headers = {"Cache-Control": "no-cache"} if path in ("sw.js", "manifest.webmanifest") else None
            return FileResponse(f, headers=headers)
        return FileResponse(web_dir / "index.html", headers={"Cache-Control": "no-cache"})
