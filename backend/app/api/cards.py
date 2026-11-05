"""Help for cards you keep failing (leeches): the design doc says to stop
drilling and help instead: show the parts, write a mnemonic from the real
components, add fresh example sentences, or suspend the card."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.tutor import _llm_errors
from app.characters import _def, family, get_index, readings_of
from app.db import get_db
from app.examples import for_unit
from app.learner import known_unit_ids
from app.llm import gateway
from app.models import AppUser, Card, Unit

router = APIRouter(prefix="/cards", tags=["cards"])


def _own(db: Session, user: AppUser, card_id: int) -> Card:
    card = db.get(Card, card_id)
    if card is None or card.user_id != user.id:
        raise HTTPException(404, "card not found")
    return card


def breakdown(db: Session, word: str) -> list[dict]:
    """Each character's parts with their meaning and role (meaning or sound)."""
    idx = get_index(db)
    out = []
    for ch in word:
        entry = idx.chars.get(ch)
        if entry is None:
            continue
        ety = entry.etymology or {}
        roles = {}
        if ety.get("type") == "pictophonetic":
            if ety.get("semantic"):
                roles[family(ety["semantic"])] = "meaning"
            if ety.get("phonetic"):
                roles[family(ety["phonetic"])] = "sound"
        out.append({
            "char": ch, "reading": (readings_of(idx, ch) or [None])[0], "definition": entry.definition,
            "parts": [{"part": p, "meaning": _def(idx, p), "reading": (readings_of(idx, p) or [None])[0],
                       "role": roles.get(family(p))} for p in entry.parts if p != ch],
            "notes": [n["text"] for n in entry.notes],
        })
    return out


@router.get("/{card_id}/help")
def help_for(card_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    card = _own(db, user, card_id)
    unit = card.unit
    examples = [e for e in for_unit(db, unit.id, known_unit_ids(db, user.id, unit.language), 4)
                if e["text"] != card.context_sentence][:2]
    return {"card_id": card.id, "headword": unit.headword, "lapses": card.lapses, "suspended": card.suspended,
            "characters": breakdown(db, unit.headword), "examples": examples,
            "mnemonic": (unit.extra or {}).get("mnemonic")}


MNEMONIC_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["mnemonic"],
                   "properties": {"mnemonic": {"type": "string"}}}

MNEMONIC_SYSTEM = """You write memory aids for a native English speaker learning Mandarin.
Write ONE short, vivid mnemonic (1-3 sentences, English) that links the word's meaning, its sound, and its characters.
Use ONLY the components listed for each character, with the meanings given; never invent parts or etymology.
If a sound part is marked, you may tie the reading to an English sound-alike. No preamble."""


@router.post("/{card_id}/mnemonic")
def mnemonic(card_id: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Generate (and keep) a mnemonic built from the word's real components."""
    card = _own(db, user, card_id)
    unit: Unit = card.unit
    parts = breakdown(db, unit.headword)
    lines = [f"Word: {unit.headword} ({unit.reading}), meaning: {'; '.join((unit.extra or {}).get('meanings', [])[:3]) or '?'}"]
    for c in parts:
        comps = ", ".join(f"{p['part']} = {p['meaning'] or '?'}" + (f" ({p['role']} part)" if p["role"] else "")
                          for p in c["parts"]) or "no separate parts"
        lines.append(f"{c['char']} ({c['reading']}, {c['definition'] or '?'}): {comps}")
    text = _llm_errors(lambda: gateway.complete_json(db, "mnemonic", MNEMONIC_SYSTEM, "\n".join(lines), MNEMONIC_SCHEMA,
                                                     user_id=user.id).data)
    m = str(text.get("mnemonic", "")).strip()
    if not m:
        raise HTTPException(502, "The model returned no mnemonic.")
    unit.extra = {**(unit.extra or {}), "mnemonic": m}
    db.commit()
    return {"mnemonic": m}


class SuspendIn(BaseModel):
    suspended: bool = True


@router.post("/{card_id}/suspend")
def suspend(card_id: int, body: SuspendIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    card = _own(db, user, card_id)
    card.suspended = body.suspended
    db.commit()
    return {"card_id": card.id, "suspended": card.suspended}
