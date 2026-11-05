"""Tutor: role-play conversations that stay inside your vocabulary.

Each turn is one model call that returns (1) a correction of what you said, in
the journal's format, so mistakes become cloze cards the same way; (2) the
tutor's in-role reply with English; (3) whether you've reached the scenario's
goal; and (4) a hint for what you could say next. Code checks the reply
against your known words, your HSK level's words and the scenario's key
phrases; if it strays, one rewrite request names the exact words to replace.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.generator import _covered, build_brief
from app.journal import CATEGORIES, SCHEMA as JOURNAL_SCHEMA, record_sentence
from app.llm import gateway
from app.models import JournalEntry, TutorSession, TutorTurn
from app.packs import get_pack
from app.packs.base import WORD


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    title_zh: str
    setting: str        # English, for the learner
    tutor_role: str     # who the tutor plays
    goal: str           # what the learner must achieve
    twist: str          # a complication the tutor introduces
    phrases: tuple[str, ...] = field(default_factory=tuple)  # key phrases the tutor may use
    level: str = "1"


SCENARIOS = [
    Scenario("restaurant", "Ordering food", "点菜", "A small restaurant. You're hungry.", "a friendly waiter",
             "Order a main dish and a drink, then ask for the bill.",
             "The first dish they ask for is sold out today; suggest something similar.",
             ("服务员", "菜单", "没有了", "要", "买单", "好吃", "喝")),
    Scenario("directions", "Asking the way", "问路", "You're lost near a subway station.", "a helpful passer-by",
             "Find out how to get to the bank, and how long it takes.",
             "The bank is a bit far; they suggest taking the subway one stop.",
             ("在哪儿", "怎么走", "往前走", "左边", "右边", "地铁站", "分钟", "远", "近")),
    Scenario("shopping", "Buying clothes", "买衣服", "A clothes shop.", "a shop assistant",
             "Buy a shirt in your size and agree on a price.",
             "Your size is only left in another colour.",
             ("多少钱", "太贵了", "便宜", "大", "小", "颜色", "试试", "块")),
    Scenario("taxi", "Taking a taxi", "坐出租车", "You get into a taxi.", "a taxi driver",
             "Tell the driver where you're going and pay at the end.",
             "There's traffic; the driver asks if you mind a slightly longer route.",
             ("去", "到了", "多少钱", "路", "堵车", "开车")),
    Scenario("new-friend", "Meeting someone new", "认识新朋友", "A friend's party.", "a friendly guest",
             "Introduce yourself, and learn their name, job and where they live.",
             "They ask what you're studying and why you're learning Chinese.",
             ("你叫什么名字", "认识你很高兴", "工作", "住", "学习", "中文")),
    Scenario("phone", "Booking on the phone", "打电话预订", "You call a restaurant to book a table.", "a receptionist",
             "Book a table for a day, time and number of people.",
             "Your first time is full; they offer half an hour later.",
             ("喂", "预订", "几位", "几点", "星期", "可以", "满了")),
    Scenario("doctor", "Seeing a doctor", "看医生", "A clinic. You've felt unwell since yesterday.", "a kind doctor",
             "Explain what's wrong and since when, and understand what to do.",
             "The doctor asks about fever and tells you to rest and drink water.",
             ("哪儿不舒服", "头疼", "发烧", "多长时间", "休息", "喝水", "药")),
    Scenario("free", "Free chat", "随便聊聊", "An easy conversation about daily life.", "a patient language partner",
             "Chat for a few turns about your day.", "Ask a follow-up question about something they said.", ()),
]
BY_ID = {s.id: s for s in SCENARIOS}
MAX_TURNS_CONTEXT = 16

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["learner", "reply", "goal_met", "hint"],
    "properties": {
        "learner": JOURNAL_SCHEMA["properties"]["sentences"]["items"],
        "reply": {"type": "object", "additionalProperties": False, "required": ["zh", "en"],
                  "properties": {"zh": {"type": "string"}, "en": {"type": "string"}}},
        "goal_met": {"type": "boolean"},
        "hint": {"type": "string"},
    },
}

SYSTEM = """You are {role} in a role-play with a beginner learner of Mandarin (around HSK {level}), a native English speaker.

Scenario: {setting}
Learner's goal: {goal}
At a natural moment: {twist}

Rules for your reply ("reply"):
- Stay in role. One or two short sentences of natural spoken Mandarin (Simplified), no pinyin.
- Use ONLY words from KNOWN WORDS, LEVEL WORDS and SCENARIO PHRASES. Names and numbers are fine. Reword rather than use another word.
- Never correct the learner inside your reply; keep the conversation going.
- "en" is a natural English translation of your reply.

Also return:
- "learner": a correction of the learner's last message, exactly as a journal correction: "original" (as written), "corrected" (minimal change, keep their meaning), "english", and "errors" ([] if none) with categories {categories}. If there is no learner message yet, use empty strings and [].
- "goal_met": true once the learner has achieved the goal.
- "hint": one short English suggestion of what the learner could say next (and how, in pinyin-free Chinese if short).

KNOWN WORDS: {known}
LEVEL WORDS: {pool}
SCENARIO PHRASES: {phrases}"""


def _history(db: Session, session: TutorSession) -> str:
    turns = list(db.scalars(select(TutorTurn).where(TutorTurn.session_id == session.id).order_by(TutorTurn.id)))
    lines = [f"{'You' if t.role == 'tutor' else 'Learner'}: {t.text}" for t in turns[-MAX_TURNS_CONTEXT:]]
    return "\n".join(lines) or "(The conversation hasn't started; open it in role.)"


def _allowed(brief, scenario: Scenario) -> set[str]:
    pack = get_pack("zh")
    phrase_words = {t.surface for p in scenario.phrases for t in pack.analyze(p) if t.kind == WORD}
    return set(brief.known) | set(brief.pool) | phrase_words | set(scenario.phrases)


def off_level(reply: str, allowed: set[str]) -> list[str]:
    out: list[str] = []
    for t in get_pack("zh").analyze(reply):
        if t.kind == WORD and not _covered(t.surface, allowed) and t.surface not in out:
            out.append(t.surface)
    return out


def _ask(db: Session, session: TutorSession, learner_text: str | None) -> tuple[dict, list[str]]:
    scenario = BY_ID[session.scenario]
    brief = build_brief(db, session.user_id, scenario.title, "dialogue", "short")
    system = SYSTEM.format(role=scenario.tutor_role, level=brief.level, setting=scenario.setting, goal=scenario.goal,
                           twist=scenario.twist, categories=", ".join(CATEGORIES),
                           known="、".join(brief.known) or "(very few yet)", pool="、".join(brief.pool[:400]),
                           phrases="、".join(scenario.phrases) or "(none)")
    user = f"Conversation so far:\n{_history(db, session)}\n\nLearner's last message: {learner_text or '(none)'}"
    cache_key = f"bhasha-tutor-{session.id}"
    data = gateway.complete_json(db, "tutor", system, user, SCHEMA, user_id=session.user_id, cache_key=cache_key).data
    allowed = _allowed(brief, scenario)
    bad = off_level(str((data.get("reply") or {}).get("zh", "")), allowed)
    if bad:
        retry = (user + f"\n\nYour reply used words the learner doesn't know: {'、'.join(bad)}. "
                 "Return the same JSON with the reply reworded to avoid them (keep the learner correction).")
        data = gateway.complete_json(db, "tutor", system, retry, SCHEMA, user_id=session.user_id, cache_key=cache_key).data
        bad = off_level(str((data.get("reply") or {}).get("zh", "")), allowed)
    return data, bad


def _tutor_turn(db: Session, session: TutorSession, data: dict, bad: list[str]) -> TutorTurn:
    reply = data.get("reply") or {}
    turn = TutorTurn(session_id=session.id, role="tutor", text=str(reply.get("zh", "")).strip() or "……",
                     english=str(reply.get("en", "")).strip(), hint=str(data.get("hint", "")).strip() or None,
                     off_level=bad)
    db.add(turn)
    return turn


def start(db: Session, user_id: int, scenario_id: str) -> TutorSession:
    if scenario_id not in BY_ID:
        raise KeyError(scenario_id)
    entry = JournalEntry(user_id=user_id, text="", source="tutor", status="done", sentences=[],
                         prompt={"scenario": scenario_id})
    db.add(entry)
    db.flush()
    session = TutorSession(user_id=user_id, scenario=scenario_id, entry_id=entry.id)
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
    entry.text = (entry.text + "\n" + text).strip()
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
