"""The one door to language models. Every feature calls complete_json here; the
gateway picks the active connection, keeps ChatGPT tokens fresh, enforces the
daily cap and logs each call to llm_call."""

import json
import time
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm import chatgpt_auth
from app.llm.errors import DailyCapError, LlmError, NoModelError, SignInRequiredError
from app.llm.providers import ChatGPTPlanProvider, Completion, OpenAICompatibleProvider
from app.models import LlmCall, LlmConnection
from app.secrets import decrypt, encrypt

# Tests (and later, a local-model override) can install a provider directly.
override = None


def active_connection(db: Session) -> LlmConnection | None:
    return db.scalar(select(LlmConnection).where(LlmConnection.active).order_by(LlmConnection.id.desc()))


def _chatgpt_token(db: Session, conn: LlmConnection):
    def access_token(force: bool) -> str:
        db.refresh(conn)
        if conn.ciphertext is None:
            raise SignInRequiredError()
        tokens = chatgpt_auth.TokenSet.from_json(decrypt(conn.ciphertext))
        if force or tokens.due():
            try:
                tokens = chatgpt_auth.refresh(tokens)
            except chatgpt_auth.GrantDeadError:
                conn.ciphertext = None
                conn.token_version += 1
                db.commit()
                raise SignInRequiredError()
            conn.ciphertext = encrypt(tokens.to_json())
            conn.token_version += 1
            db.commit()
        return tokens.access_token

    return access_token


def provider_for(db: Session, conn: LlmConnection | None = None):
    if override is not None:
        return override
    conn = conn or active_connection(db)
    if conn is None:
        raise NoModelError()
    if conn.kind == "chatgpt":
        if conn.ciphertext is None:
            raise SignInRequiredError()
        return ChatGPTPlanProvider(conn.base_url, _chatgpt_token(db, conn))
    key = json.loads(decrypt(conn.ciphertext)).get("api_key") if conn.ciphertext else None
    return OpenAICompatibleProvider(conn.base_url, key)


def _calls_today(db: Session) -> int:
    tz = ZoneInfo(get_settings().timezone)
    start = datetime.combine(datetime.now(tz).date(), dtime(0), tz).astimezone(timezone.utc)
    return db.scalar(select(func.count()).select_from(LlmCall).where(LlmCall.created_at >= start)) or 0


def complete_json(db: Session, feature: str, system: str, user: str, schema: dict,
                  user_id: int | None = None, cache_key: str | None = None) -> Completion:
    cap = get_settings().llm_max_calls_per_day
    if _calls_today(db) >= cap:
        raise DailyCapError(cap)
    conn = active_connection(db)
    provider = provider_for(db, conn)
    model = (conn.model if conn else None) or "fake-model"
    if conn is not None and not conn.model:
        raise LlmError("Pick a model in Progress → Text generation.")
    t0 = time.monotonic()
    result = provider.complete_json(model, system, user, schema, cache_key=cache_key)
    db.add(LlmCall(user_id=user_id, feature=feature, model=result.model, input_tokens=result.input_tokens,
                   output_tokens=result.output_tokens, cache_read_tokens=result.cached_tokens,
                   # Plan usage has no per-token price; LM Studio is free. API-key pricing: TODO.
                   cost_usd=0))
    db.commit()
    result.seconds = time.monotonic() - t0  # type: ignore[attr-defined]
    return result
