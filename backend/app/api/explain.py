"""Explain this: ask why a sentence works the way it does, answered at your level.

The model explains; it never supplies pinyin (the reader's local data does).
Grammar points link to the Chinese Grammar Wiki (CC BY-NC-SA): we link, never copy."""

from urllib.parse import quote

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.tutor import _llm_errors
from app.db import get_db
from app.llm import gateway
from app.models import AppUser

router = APIRouter(tags=["explain"])

WIKI_SEARCH = "https://resources.allsetlearning.com/chinese/grammar/Special:Search?search="

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["answer", "chunks", "points"],
    "properties": {
        "answer": {"type": "string"},
        "chunks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["zh", "role"],
                                              "properties": {"zh": {"type": "string"}, "role": {"type": "string"}}}},
        "points": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["name", "search"],
                                              "properties": {"name": {"type": "string"}, "search": {"type": "string"}}}},
    },
}

SYSTEM = """You explain Mandarin (Simplified) to a native English speaker who is a beginner (around HSK {level}).
Answer the learner's question about the sentence in plain English, at most about 120 words. Avoid jargon or explain it
in passing. Never write pinyin or tone marks (the app shows pronunciation itself); Chinese characters are fine.
"chunks": the sentence split into its meaningful pieces in order, each with a short English role
(e.g. "time: yesterday", "verb + 了: went (completed)"). The chunks, joined, must equal the sentence.
"points": 0-3 grammar points involved, each with a short English name and a search phrase for the Chinese Grammar
Wiki (e.g. "了 completed action", "time words before verb")."""


class ExplainIn(BaseModel):
    sentence: str = Field(min_length=1, max_length=300)
    question: str = Field(default="Explain this sentence.", max_length=300)
    focus: str | None = Field(default=None, max_length=40)


@router.post("/explain")
def explain(body: ExplainIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    from app.journal import _level

    q = body.question.strip() or "Explain this sentence."
    user_msg = f"Sentence: {body.sentence.strip()}\n" + (f"Word in focus: {body.focus}\n" if body.focus else "") + f"Question: {q}"
    data = _llm_errors(lambda: gateway.complete_json(
        db, "explain", SYSTEM.format(level=_level(db, user.id)), user_msg, SCHEMA, user_id=user.id).data)
    chunks = [{"zh": str(c.get("zh", "")), "role": str(c.get("role", ""))} for c in data.get("chunks") or []]
    # Drop the breakdown if it doesn't actually rebuild the sentence (a model slip).
    if "".join(c["zh"] for c in chunks).replace(" ", "") != body.sentence.strip().replace(" ", ""):
        chunks = []
    return {
        "answer": str(data.get("answer", "")).strip(),
        "chunks": chunks,
        "points": [{"name": str(p.get("name", "")), "url": WIKI_SEARCH + quote(str(p.get("search") or p.get("name") or ""))}
                   for p in (data.get("points") or [])[:3] if p.get("name")],
    }
