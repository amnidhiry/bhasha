import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.config import get_settings
from app.db import get_db
from app.llm import chatgpt_auth, gateway
from app.llm.errors import LlmError
from app.models import AppUser, LlmCall, LlmConnection
from app.secrets import SecretKeyMissingError, decrypt, encrypt

router = APIRouter(prefix="/llm", tags=["llm"])


def _status(db: Session) -> dict:
    conn = gateway.active_connection(db)
    calls_today = gateway._calls_today(db)
    tokens = db.execute(select(func.coalesce(func.sum(LlmCall.input_tokens), 0),
                               func.coalesce(func.sum(LlmCall.output_tokens), 0))).one()
    base = {"calls_today": calls_today, "daily_cap": get_settings().llm_max_calls_per_day,
            "tokens_in_total": tokens[0], "tokens_out_total": tokens[1],
            "secret_key_set": bool(get_settings().secret_key)}
    if conn is None:
        return {**base, "connected": False}
    return {**base, "connected": conn.ciphertext is not None or conn.kind != "chatgpt", "kind": conn.kind,
            "label": conn.label, "email": conn.account_email, "model": conn.model, "base_url": conn.base_url}


@router.get("/status")
def status(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    return _status(db)


def _activate(db: Session, conn: LlmConnection) -> None:
    db.execute(update(LlmConnection).values(active=False))
    conn.active = True
    db.add(conn)
    db.flush()


def _pick_default_model(db: Session, conn: LlmConnection) -> None:
    try:
        models = gateway.provider_for(db, conn).models()
    except Exception:  # listing is a convenience; the user can pick later
        return
    if models and not conn.model:
        conn.model = models[0]["id"]


@router.post("/chatgpt/start")
def chatgpt_start(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    existing = db.scalar(select(LlmConnection).where(LlmConnection.kind == "chatgpt"))
    returning = None
    try:
        if existing is not None and existing.ciphertext:
            returning = chatgpt_auth.TokenSet.from_json(decrypt(existing.ciphertext))
        flow = chatgpt_auth.start(returning)
    except SecretKeyMissingError as e:
        raise HTTPException(400, str(e))
    except Exception:
        flow = chatgpt_auth.start(None)
    return {"flow_id": flow.id, "authorize_url": flow.url, "redirect_uri": chatgpt_auth.redirect_uri()}


class FinishIn(BaseModel):
    flow_id: str
    address: str = Field(min_length=10, max_length=8192)


@router.post("/chatgpt/finish")
def chatgpt_finish(body: FinishIn, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    try:
        tokens = chatgpt_auth.finish(body.flow_id, body.address)
    except chatgpt_auth.SignInFailedError as e:
        raise HTTPException(400, str(e))
    except chatgpt_auth.GrantDeadError:
        raise HTTPException(400, "OpenAI refused the sign-in code. Start again.")
    except Exception:
        raise HTTPException(502, "OpenAI could not be reached to finish the sign-in.")
    conn = db.scalar(select(LlmConnection).where(LlmConnection.kind == "chatgpt"))
    if conn is None:
        conn = LlmConnection(kind="chatgpt", label="ChatGPT", base_url=get_settings().chatgpt_api_url)
    conn.ciphertext = encrypt(tokens.to_json())
    conn.token_version = (conn.token_version or 0) + 1
    conn.account_email = tokens.email
    _activate(db, conn)
    db.commit()
    _pick_default_model(db, conn)
    db.commit()
    return _status(db)


class CompatibleIn(BaseModel):
    base_url: str = Field(description="e.g. http://lmstudio.lan:1234/v1 or https://api.openai.com/v1")
    api_key: str | None = None
    model: str | None = None
    label: str = "OpenAI-compatible"


@router.post("/openai-compatible")
def connect_compatible(body: CompatibleIn, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    conn = LlmConnection(kind="openai_compatible", label=body.label, base_url=body.base_url.rstrip("/"),
                         model=body.model,
                         ciphertext=encrypt(json.dumps({"api_key": body.api_key})) if body.api_key else None)
    _activate(db, conn)
    db.commit()
    _pick_default_model(db, conn)
    db.commit()
    return _status(db)


@router.get("/models")
def models(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    try:
        return gateway.provider_for(db).models()
    except LlmError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(502, f"Couldn't list models: {e}")


class ModelIn(BaseModel):
    model: str = Field(min_length=1, max_length=128)


@router.put("/model")
def set_model(body: ModelIn, db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    conn = gateway.active_connection(db)
    if conn is None:
        raise HTTPException(409, "No model connection.")
    conn.model = body.model
    db.commit()
    return _status(db)


@router.post("/signout")
def sign_out(db: Session = Depends(get_db), _: AppUser = Depends(current_user)):
    conn = gateway.active_connection(db)
    if conn is not None:
        if conn.kind == "chatgpt" and conn.ciphertext:
            try:
                chatgpt_auth.revoke(chatgpt_auth.TokenSet.from_json(decrypt(conn.ciphertext)))
            except Exception:
                pass
        db.delete(conn)
        db.commit()
    return _status(db)
