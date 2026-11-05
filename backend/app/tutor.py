"""Tutor: role-play conversations that stay inside your vocabulary.

Each turn is one model call that returns (1) a correction of what you said, in
the journal's format, so mistakes become cloze cards the same way; (2) the
tutor's in-role reply with English; (3) whether you've reached the scenario's
goal; and (4) a hint for what you could say next. Code checks the reply
against your known words, your level's words and the scenario's key phrases;
if it strays, one rewrite request names the exact words to replace. Scenarios
come from the language pack.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.generator import build_brief
from app.journal import categories, schema as journal_schema, record_sentence
from app.llm import gateway
from app.models import JournalEntry, TutorSession, TutorTurn
from app.packs import get_pack
from app.packs.base import WORD, Scenario


def scenarios(language: str) -> dict[str, Scenario]:
    return {s.id: s for s in get_pack(language).scenarios()}


MAX_TURNS_CONTEXT = 16


def schema(language: str) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["learner", "reply", "goal_met", "hint"],
        "properties": {
            "learner": journal_schema(language)["properties"]["sentences"]["items"],
            "reply": {"type": "object", "additionalProperties": False, "required": ["text", "en"],
                      "properties": {"text": {"type": "string"}, "en": {"type": "string"}}},
            "goal_met": {"type": "boolean"},
            "hint": {"type": "string"},
        },
    }


SYSTEM = """You are {role} in a role-play with a beginner learner of {language} (around {framework} {level}), a native English speaker.

Scenario: {setting}
Learner's goal: {goal}
At a natural moment: {twist}

Rules for your reply ("reply"):
- Stay in role. One or two short sentences of natural spoken {language}. {no_aid}{note}
- Use ONLY words from KNOWN WORDS, LEVEL WORDS and SCENARIO PHRASES. Names and numbers are fine. Reword rather than use another word.
- Never correct the learner inside your reply; keep the conversation going.
- "en" is a natural English translation of your reply.

Also return:
- "learner": a correction of the learner's last message, exactly as a journal correction: "original" (as written), "corrected" (minimal change, keep their meaning), "english", and "errors" ([] if none) with categories {categories}. If there is no learner message yet, use empty strings and [].
- "goal_met": true once the learner has achieved the goal.
- "hint": one short English suggestion of what the learner could say next (and how, in {language} if short, with no reading aid).

KNOWN WORDS: {known}
LEVEL WORDS: {pool}
SCENARIO PHRASES: {phrases}"""


def _history(db: Session, session: TutorSession) -> str:
    turns = list(db.scalars(select(TutorTurn).where(TutorTurn.session_id == session.id).order_by(TutorTurn.id)))
    lines = [f"{'You' if t.role == 'tutor' else 'Learner'}: {t.text}" for t in turns[-MAX_TURNS_CONTEXT:]]
    return "\n".join(lines) or "(The conversation hasn't started; open it in role.)"


def _allowed(brief, scenario: Scenario, language: str = "zh") -> set[str]:
    pack = get_pack(language)
    phrase_words = {t.head for p in scenario.phrases for t in pack.analyze(p) if t.kind == WORD}
    return set(brief.known) | set(brief.pool) | phrase_words | set(scenario.phrases)


def off_level(reply: str, allowed: set[str], language: str = "zh") -> list[str]:
    pack = get_pack(language)
    out: list[str] = []
    for t in pack.analyze(reply):
        if t.kind == WORD and not pack.covered(t.head, allowed) and t.head not in out:
            out.append(t.head)
    return out


def _reply_text(data: dict) -> str:
    return str((data.get("reply") or {}).get("text", ""))


def _ask(db: Session, session: TutorSession, learner_text: str | None) -> tuple[dict, list[str]]:
    lang = session.language
    pack = get_pack(lang)
    pr, j = pack.prompts, pack.prompts.list_joiner
    scenario = scenarios(lang)[session.scenario]
    brief = build_brief(db, session.user_id, scenario.title, "dialogue", "short", language=lang)
    system = SYSTEM.format(role=scenario.tutor_role, language=pr.language_name, framework=pack.levels.name or "level",
                           level=brief.level, setting=scenario.setting, goal=scenario.goal, twist=scenario.twist,
                           no_aid=pr.no_reading_aid_rule, note=(" " + pr.learner_note) if pr.learner_note else "",
                           categories=", ".join(categories(lang)),
                           known=j.join(brief.known) or "(very few yet)", pool=j.join(brief.pool[:400]),
                           phrases=j.join(scenario.phrases) or "(none)")
    user = f"Conversation so far:\n{_history(db, session)}\n\nLearner's last message: {learner_text or '(none)'}"
    cache_key = f"bhasha-tutor-{session.id}"
    sch = schema(lang)
    data = gateway.complete_json(db, "tutor", system, user, sch, user_id=session.user_id, cache_key=cache_key).data
    allowed = _allowed(brief, scenario, lang)
    bad = off_level(_reply_text(data), allowed, lang)
    if bad:
        retry = (user + f"\n\nYour reply used words the learner doesn't know: {j.join(bad)}. "
                 "Return the same JSON with the reply reworded to avoid them (keep the learner correction).")
        data = gateway.complete_json(db, "tutor", system, retry, sch, user_id=session.user_id, cache_key=cache_key).data
        bad = off_level(_reply_text(data), allowed, lang)
    return data, bad


def _tutor_turn(db: Session, session: TutorSession, data: dict, bad: list[str]) -> TutorTurn:
    reply = data.get("reply") or {}
    turn = TutorTurn(session_id=session.id, role="tutor", text=str(reply.get("text", "")).strip() or "…",
                     english=str(reply.get("en", "")).strip(), hint=str(data.get("hint", "")).strip() or None,
                     off_level=bad)
    db.add(turn)
    return turn


def start(db: Session, user_id: int, scenario_id: str, language: str = "zh") -> TutorSession:
    if scenario_id not in scenarios(language):
        raise KeyError(scenario_id)
    entry = JournalEntry(user_id=user_id, language=language, text="", source="tutor", status="done", sentences=[],
                         prompt={"scenario": scenario_id})
    db.add(entry)
    db.flush()
    session = TutorSession(user_id=user_id, language=language, scenario=scenario_id, entry_id=entry.id)
    db.add(session)
    db.flush()
    data, bad = _ask(db, session, None)
    _tutor_turn(db, session, data, bad)
    db.commit()
    return session


def say(db: Session, session: TutorSession, text: str) -> tuple[TutorTurn, TutorTurn, list]:
    """The learner speaks; returns (learner turn, tutor turn, verified errors)."""
    text = text.strip()
    data, bad = _ask(db, session, text)
    fix = data.get("learner") or {}
    entry = db.get(JournalEntry, session.entry_id)
    corrected = str(fix.get("corrected", "")).strip() or text
    errors = record_sentence(db, entry, text, corrected, str(fix.get("english", "")), fix.get("errors") or [])
    entry.text = (entry.text + "\n" + text).strip()  # one line per turn
    entry.corrected = "\n".join(s["corrected"] for s in entry.sentences)
    mine = TutorTurn(session_id=session.id, role="learner", text=text, corrected=corrected,
                     english=str(fix.get("english", "")).strip())
    db.add(mine)
    theirs = _tutor_turn(db, session, data, bad)
    if data.get("goal_met"):
        session.goal_met = True
    db.commit()
    return mine, theirs, errors


def end(db: Session, session: TutorSession) -> TutorSession:
    session.status = "ended"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()
    return session
