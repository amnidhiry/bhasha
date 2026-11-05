from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import tutor
from app.api.deps import current_user
from app.api.jobs import _require_model
from app.db import get_db
from app.journal import CATEGORIES
from app.llm.errors import DailyCapError, LlmError, NoModelError, PlanLimitError, SignInRequiredError
from app.models import AppUser, ErrorItem, TutorSession, TutorTurn
from app.packs import get_pack
from app.reader import resolve_units, unit_statuses

router = APIRouter(prefix="/tutor", tags=["tutor"])


def _llm_errors(fn):
    try:
        return fn()
    except (SignInRequiredError, NoModelError) as e:
        raise HTTPException(409, str(e))
    except (PlanLimitError, DailyCapError) as e:
        raise HTTPException(429, str(e))
    except LlmError as e:
        raise HTTPException(502, str(e))


def _tokens(db: Session, user_id: int, text: str) -> list[dict]:
    toks = get_pack("zh").analyze(text)
    unit_ids = resolve_units(db, "zh", toks)
    statuses = unit_statuses(db, user_id, "zh", {u for u in unit_ids if u})
    return [{"surface": t.surface, "kind": t.kind, "unit_id": u, "status": statuses.get(u) if u else None,
             "show_reading": t.kind == "proper" or (u is not None and statuses.get(u) in ("new", "learning")),
             "syllables": [s.__dict__ for s in t.syllables]} for t, u in zip(toks, unit_ids)]


def _session(db: Session, user_id: int, s: TutorSession) -> dict:
    sc = tutor.BY_ID[s.scenario]
    turns = list(db.scalars(select(TutorTurn).where(TutorTurn.session_id == s.id).order_by(TutorTurn.id)))
    errors = list(db.scalars(select(ErrorItem).where(ErrorItem.entry_id == s.entry_id).order_by(ErrorItem.id))) \
        if s.entry_id else []
    out, learner_i = [], 0
    for t in turns:
        d = {"id": t.id, "role": t.role, "text": t.text, "english": t.english}
        if t.role == "tutor":
            d |= {"tokens": _tokens(db, user_id, t.text), "hint": t.hint, "off_level": t.off_level}
        else:
            d |= {"corrected": t.corrected,
                  "errors": [{"category": e.category, "label": CATEGORIES.get(e.category, e.category), "wrong": e.wrong,
                              "right": e.right, "explanation": e.explanation, "card_id": e.card_id}
                             for e in errors if e.sentence_index == learner_i]}
            learner_i += 1
        out.append(d)
    db.commit()  # resolve_units may have created units for new words
    return {"id": s.id, "scenario": _scenario(sc), "status": s.status, "goal_met": s.goal_met, "turns": out,
            "mistakes": len(errors)}


def _scenario(sc: tutor.Scenario) -> dict:
    return {"id": sc.id, "title": sc.title, "title_zh": sc.title_zh, "setting": sc.setting, "goal": sc.goal,
            "role": sc.tutor_role}


@router.get("/scenarios")
def scenarios(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    done = dict(db.execute(select(TutorSession.scenario, func.count()).where(
        TutorSession.user_id == user.id, TutorSession.goal_met).group_by(TutorSession.scenario)).all())
    return [{**_scenario(s), "completed": done.get(s.id, 0)} for s in tutor.SCENARIOS]


class StartIn(BaseModel):
    scenario: str


@router.post("/sessions")
def start(body: StartIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    """Start a role-play; the tutor speaks first. Takes a few seconds (one model call)."""
    if body.scenario not in tutor.BY_ID:
        raise HTTPException(404, "no such scenario")
    _require_model(db)
    s = _llm_errors(lambda: tutor.start(db, user.id, body.scenario))
    return _session(db, user.id, s)


def _own(db: Session, user: AppUser, sid: int) -> TutorSession:
    s = db.get(TutorSession, sid)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "session not found")
    return s


@router.get("/sessions")
def sessions(db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    rows = db.scalars(select(TutorSession).where(TutorSession.user_id == user.id)
                      .order_by(TutorSession.created_at.desc()).limit(20))
    return [{"id": s.id, "scenario": _scenario(tutor.BY_ID[s.scenario]), "status": s.status, "goal_met": s.goal_met,
             "created_at": s.created_at} for s in rows]


@router.get("/sessions/{sid}")
def get_session(sid: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    return _session(db, user.id, _own(db, user, sid))


class SayIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)


@router.post("/sessions/{sid}/turns")
def say(sid: int, body: SayIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    s = _own(db, user, sid)
    if s.status != "active":
        raise HTTPException(409, "this conversation has ended")
    _llm_errors(lambda: tutor.say(db, s, body.text))
    return _session(db, user.id, s)


@router.post("/sessions/{sid}/end")
def end(sid: int, db: Session = Depends(get_db), user: AppUser = Depends(current_user)):
    return _session(db, user.id, tutor.end(db, _own(db, user, sid)))
