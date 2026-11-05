from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import tutor
from app.api.deps import current_language, current_user
from app.api.jobs import _require_model
from app.db import get_db
from app.journal import categories
from app.llm.errors import DailyCapError, LlmError, NoModelError, PlanLimitError, SignInRequiredError
from app.models import AppUser, ErrorItem, TutorSession, TutorTurn
from app.packs import get_pack
from app.packs.base import Scenario
from app.reader import resolve_units, token_dict, unit_statuses

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


def _tokens(db: Session, user_id: int, text: str, language: str) -> list[dict]:
    toks = get_pack(language).analyze(text)
    unit_ids = resolve_units(db, language, toks)
    statuses = unit_statuses(db, user_id, language, {u for u in unit_ids if u})
    return [token_dict(t, u, statuses.get(u) if u else None) for t, u in zip(toks, unit_ids)]


def _session(db: Session, user_id: int, s: TutorSession) -> dict:
    sc = tutor.scenarios(s.language)[s.scenario]
    labels = categories(s.language)
    turns = list(db.scalars(select(TutorTurn).where(TutorTurn.session_id == s.id).order_by(TutorTurn.id)))
    errors = list(db.scalars(select(ErrorItem).where(ErrorItem.entry_id == s.entry_id).order_by(ErrorItem.id))) \
        if s.entry_id else []
    out, learner_i = [], 0
    for t in turns:
        d = {"id": t.id, "role": t.role, "text": t.text, "english": t.english}
        if t.role == "tutor":
            d |= {"tokens": _tokens(db, user_id, t.text, s.language), "hint": t.hint, "off_level": t.off_level}
        else:
            d |= {"corrected": t.corrected,
                  "errors": [{"category": e.category, "label": labels.get(e.category, e.category), "wrong": e.wrong,
                              "right": e.right, "explanation": e.explanation, "card_id": e.card_id}
                             for e in errors if e.sentence_index == learner_i]}
            learner_i += 1
        out.append(d)
    db.commit()  # resolve_units may have created units for new words
    return {"id": s.id, "language": s.language, "scenario": _scenario(sc), "status": s.status, "goal_met": s.goal_met, "turns": out,
            "mistakes": len(errors)}


def _scenario(sc: Scenario) -> dict:
    return {"id": sc.id, "title": sc.title, "title_native": sc.title_native, "setting": sc.setting, "goal": sc.goal,
            "role": sc.tutor_role, "level": sc.level}


@router.get("/scenarios")
def scenarios(db: Session = Depends(get_db), user: AppUser = Depends(current_user),
              lang: str = Depends(current_language)):
    done = dict(db.execute(select(TutorSession.scenario, func.count()).where(
        TutorSession.user_id == user.id, TutorSession.language == lang, TutorSession.goal_met)
        .group_by(TutorSession.scenario)).all())
    return [{**_scenario(s), "completed": done.get(s.id, 0)} for s in tutor.scenarios(lang).values()]


class StartIn(BaseModel):
    scenario: str


@router.post("/sessions")
def start(body: StartIn, db: Session = Depends(get_db), user: AppUser = Depends(current_user),
          lang: str = Depends(current_language)):
    """Start a role-play; the tutor speaks first. Takes a few seconds (one model call)."""
    if body.scenario not in tutor.scenarios(lang):
        raise HTTPException(404, "no such scenario")
    _require_model(db)
    s = _llm_errors(lambda: tutor.start(db, user.id, body.scenario, lang))
    return _session(db, user.id, s)


def _own(db: Session, user: AppUser, sid: int) -> TutorSession:
    s = db.get(TutorSession, sid)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "session not found")
    return s


@router.get("/sessions")
def sessions(db: Session = Depends(get_db), user: AppUser = Depends(current_user),
             lang: str = Depends(current_language)):
    rows = db.scalars(select(TutorSession).where(TutorSession.user_id == user.id, TutorSession.language == lang)
                      .order_by(TutorSession.created_at.desc()).limit(20))
    by_id = tutor.scenarios(lang)
    return [{"id": s.id, "scenario": _scenario(by_id[s.scenario]), "status": s.status, "goal_met": s.goal_met,
             "created_at": s.created_at} for s in rows if s.scenario in by_id]


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
