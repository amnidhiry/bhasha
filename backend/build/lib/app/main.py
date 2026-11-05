from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import lookup, mine, progress, reviews, texts
from app.bootstrap import ensure_defaults, warm_packs
from app.db import SessionLocal


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as db:
        ensure_defaults(db)
        warm_packs(db)
    yield


app = FastAPI(title="bhasha", version="0.1.0", lifespan=lifespan)
for r in (reviews.router, texts.router, lookup.router, mine.router, progress.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"ok": True}
