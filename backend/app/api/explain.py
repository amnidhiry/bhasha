"""Explain this: ask why a sentence works the way it does, answered at your level.

The model explains; it never supplies a reading aid (the reader's local data does).
Grammar points link to the pack's grammar reference (zh: the Chinese Grammar Wiki,
CC BY-NC-SA): we link, never copy."""

from urllib.parse import quote

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import current_language, current_user
from app.api.tutor import _llm_errors
from app.db import get_db
from app.llm import gateway
from app.models import AppUser
from app.packs import get_pack

router = APIRouter(tags=["explain"])

SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["answer", "chunks", "points"],
    "properties": {
        "answer": {"type": "string"},
        "chunks": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["text", "role"],
                                              "properties": {"text": {"type": "string"}, "role": {"type": "string"}}}},
        "points": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                              "required": ["name", "search"],
                                              "properties": {"name": {"type": "string"}, "search": {"type": "string"}}}},
    },
}

SYSTEM = """You explain {language} to a native English speaker who is a beginner (around {framework} {level}).
Answer the learner's question about the sentence in plain English, at most about 120 words. Avoid jargon or explain it
in passing. {no_aid} Words in the target script are fine.
"chunks": the sentence split into its meaningful pieces in order, each with a short English role
(e.g. "time: yesterday", "verb + past marker: went"). The chunks, joined, must equal the sentence.
"points": 0-3 grammar points involved, each with a short English name and a short search phrase for a grammar
reference (e.g. "past tense", "word order of time words")."""


class ExplainIn(BaseModel):
    sentence: str = Field(min_length=1, max_length=300)
    question: str = Field(default="Explain this sentence.", max_length=300)
    focus: str | None = Field(default=None, max_length=40)


@router.post("/explain")
def explain(body: ExplainIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user),
            lang: str = Depends(current_language)):
    from app.journal import _level

    pack = get_pack(lang)
    system = SYSTEM.format(language=pack.prompts.language_name, framework=pack.levels.name or "level",
                           level=_level(db, user.id, lang), no_aid=pack.prompts.no_reading_aid_rule)
    q = body.question.strip() or "Explain this sentence."
    user_msg = f"Sentence: {body.sentence.strip()}\n" + (f"Word in focus: {body.focus}\n" if body.focus else "") + f"Question: {q}"
    data = _llm_errors(lambda: gateway.complete_json(
        db, "explain", system, user_msg, SCHEMA, user_id=user.id).data)
    chunks = [{"text": str(c.get("text", "")), "role": str(c.get("role", ""))} for c in data.get("chunks") or []]
    # Drop the breakdown if it doesn't actually rebuild the sentence (a model slip).
    if "".join(c["text"] for c in chunks).replace(" ", "") != body.sentence.strip().replace(" ", ""):
        chunks = []
    return {
        "answer": str(data.get("answer", "")).strip(),
        "chunks": chunks,
        "points": [{"name": str(p.get("name", "")),
                    "url": (pack.grammar_search + quote(str(p.get("search") or p.get("name") or "")))
                    if pack.grammar_search else None}
                   for p in (data.get("points") or [])[:3] if p.get("name")],
    }
