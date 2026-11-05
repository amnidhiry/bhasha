"""Sign in with ChatGPT: use a ChatGPT Plus/Pro plan for model calls, no API key.

Protocol adapted from SurfSense (Apache-2.0,
surfsense_local/backend/modules/llm/subscriptions/chatgpt), which follows
OpenAI's "Sign in with ChatGPT" docs for open-source apps
(developers.openai.com/siwc/token-sharing-open-source). OpenAI calls this a
preview; check those docs if a step starts failing.

Flow (OAuth 2 authorization code + PKCE, public client):
1. The first sign-in registers this install dynamically (client_id
   "dynamic_agent_client"); OpenAI returns the real client_id on the callback.
2. The redirect goes to a loopback address. On a homelab nothing listens
   there, so the browser shows a "can't connect" page: the person pastes that
   address back into bhasha, which finishes the exchange. The code is useless
   without the PKCE verifier, which never leaves this process.
3. Tokens are stored encrypted and refreshed shortly before expiry.
"""

import base64
import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass, field, replace
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.config import get_settings
from app.secrets import install_uuid

DYNAMIC_CLIENT = "dynamic_agent_client"
AGENT_NAME = "bhasha"
RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
SCOPE = f"openid profile email offline_access resource.invoke {PLAN_SCOPE}"
CALLBACK_PATH = "/callback"
REFRESH_EARLY_SECONDS = 300
LEEWAY_SECONDS = 120
SIGN_IN_SECONDS = 600
# OpenAI's codes for a grant that cannot be refreshed again.
DEAD_GRANT = {"invalid_grant", "token_expired", "refresh_token_invalidated"}

# Tests swap this for an httpx.MockTransport.
transport: httpx.BaseTransport | None = None


class SignInFailedError(Exception):
    pass


class GrantDeadError(Exception):
    """OpenAI will not refresh this grant; sign in again."""


def _auth_url() -> str:
    return get_settings().chatgpt_auth_url.rstrip("/")


def _client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0), transport=transport)


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


@dataclass(frozen=True)
class Pkce:
    verifier: str = field(default_factory=lambda: secrets.token_urlsafe(48))
    state: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    nonce: str = field(default_factory=lambda: secrets.token_urlsafe(32))

    @property
    def challenge(self) -> str:
        return base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode()).digest()).rstrip(b"=").decode()


@dataclass(frozen=True)
class TokenSet:
    client_id: str
    access_token: str
    refresh_token: str
    id_token: str
    expires_at: float
    account: str
    email: str | None = None
    earliest_refresh_at: float | None = None

    def due(self, now: float | None = None) -> bool:
        now = time.time() if now is None else now
        if self.earliest_refresh_at is not None and now < self.earliest_refresh_at:
            return False
        return now >= self.expires_at - REFRESH_EARLY_SECONDS

    def refreshed(self, reply: dict, now: float | None = None) -> "TokenSet":
        now = time.time() if now is None else now
        earliest = reply.get("earliest_refresh_at")
        return replace(
            self,
            access_token=reply["access_token"],
            refresh_token=reply.get("refresh_token") or self.refresh_token,
            id_token=reply.get("id_token") or self.id_token,
            expires_at=now + float(reply.get("expires_in") or 3600),
            earliest_refresh_at=float(earliest) if isinstance(earliest, (int, float)) else None,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "TokenSet":
        return cls(**json.loads(raw))


def redirect_uri() -> str:
    return f"http://127.0.0.1:{get_settings().chatgpt_redirect_port}{CALLBACK_PATH}"


def authorize_url(pkce: Pkce, returning: TokenSet | None = None) -> str:
    query = {
        "client_id": returning.client_id if returning else DYNAMIC_CLIENT,
        "agent_name_hint": AGENT_NAME,
        "ext_agent_host_id": install_uuid("chatgpt-ext-agent-host-id"),
        "response_type": "code",
        "redirect_uri": redirect_uri(),
        "scope": SCOPE,
        "resource": RESOURCE,
        "state": pkce.state,
        "nonce": pkce.nonce,
        "code_challenge_method": "S256",
        "code_challenge": pkce.challenge,
    }
    if returning:
        query["id_token_hint"] = returning.id_token
    return f"{_auth_url()}/api/accounts/authorize?{urlencode(query)}"


def _token_reply(reply: httpx.Response) -> dict:
    if reply.status_code in (400, 401):
        try:
            error = reply.json().get("error")
        except ValueError:
            error = None
        if error in DEAD_GRANT:
            raise GrantDeadError(error)
    reply.raise_for_status()
    payload = reply.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise SignInFailedError("OpenAI's token endpoint returned no access token.")
    return payload


def refresh(tokens: TokenSet) -> TokenSet:
    with _client(10.0) as c:
        reply = c.post(f"{_auth_url()}/api/accounts/oauth/token", data={
            "grant_type": "refresh_token",
            "client_id": tokens.client_id,
            "refresh_token": tokens.refresh_token,
            "resource": RESOURCE,
        })
    return tokens.refreshed(_token_reply(reply))


def revoke(tokens: TokenSet) -> None:
    """Best effort: the local sign-out stands whatever OpenAI answers."""
    try:
        with _client(5.0) as c:
            c.post(f"{_auth_url()}/api/accounts/oauth/revoke", data={
                "token": tokens.refresh_token, "token_type_hint": "refresh_token", "client_id": tokens.client_id,
            })
    except httpx.HTTPError:
        pass


def verified_claims(id_token: str, client_id: str, nonce: str) -> dict:
    """RS256 signature, issuer, audience, expiry and nonce, as OpenAI's docs ask."""
    try:
        header_b64, claims_b64, sig_b64 = id_token.split(".")
        header = json.loads(_unb64(header_b64))
        claims = json.loads(_unb64(claims_b64))
    except ValueError as error:
        raise SignInFailedError("OpenAI's ID token is malformed.") from error
    if header.get("alg") != "RS256":
        raise SignInFailedError("OpenAI's ID token is not RS256-signed.")
    with _client(10.0) as c:
        keys = c.get(f"{_auth_url()}/.well-known/jwks.json").raise_for_status().json().get("keys", [])
    key = next((k for k in keys if k.get("kty") == "RSA" and k.get("kid") == header.get("kid")), None)
    if key is None:
        raise SignInFailedError("OpenAI's ID token signing key is not published.")
    public = rsa.RSAPublicNumbers(int.from_bytes(_unb64(key["e"]), "big"),
                                  int.from_bytes(_unb64(key["n"]), "big")).public_key()
    try:
        public.verify(_unb64(sig_b64), f"{header_b64}.{claims_b64}".encode(), padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as error:
        raise SignInFailedError("OpenAI's ID token signature does not verify.") from error
    aud = claims.get("aud")
    if claims.get("iss") != _auth_url():
        raise SignInFailedError("The ID token is from another issuer.")
    if client_id not in (aud if isinstance(aud, list) else [aud]):
        raise SignInFailedError("The ID token is for another client.")
    if not isinstance(claims.get("exp"), (int, float)) or claims["exp"] + LEEWAY_SECONDS < time.time():
        raise SignInFailedError("The ID token has expired.")
    if claims.get("nonce") != nonce:
        raise SignInFailedError("The ID token answers a different sign-in.")
    if not isinstance(claims.get("sub"), str):
        raise SignInFailedError("The ID token names no account.")
    return claims


@dataclass
class Flow:
    id: str
    pkce: Pkce
    url: str
    returning: TokenSet | None
    started: float = field(default_factory=time.time)


_flows: dict[str, Flow] = {}


def start(returning: TokenSet | None = None) -> Flow:
    now = time.time()
    for fid in [k for k, f in _flows.items() if now - f.started > SIGN_IN_SECONDS]:
        del _flows[fid]
    pkce = Pkce()
    flow = Flow(secrets.token_urlsafe(16), pkce, authorize_url(pkce, returning), returning)
    _flows[flow.id] = flow
    return flow


def finish(flow_id: str, pasted_address: str) -> TokenSet:
    """Complete a sign-in from the address the browser was redirected to."""
    flow = _flows.get(flow_id)
    if flow is None:
        raise SignInFailedError("This sign-in expired. Start again.")
    try:
        target = urlsplit(pasted_address.strip())
    except ValueError as error:
        raise SignInFailedError("That isn't the address from the sign-in tab.") from error
    query = {k: v[0] for k, v in parse_qs(target.query).items()}
    if target.path != CALLBACK_PATH or "state" not in query:
        raise SignInFailedError("Paste the full address of the tab that opened after you approved (it starts with http://127.0.0.1).")
    if query["state"] != flow.pkce.state:
        raise SignInFailedError("That address answers a different sign-in. Start again.")
    if "error" in query:
        raise SignInFailedError(query.get("error_description") or "The sign-in was declined.")
    client_id, code = query.get("client_id"), query.get("code")
    if not client_id or not code:
        raise SignInFailedError("OpenAI's answer carried no sign-in code.")
    if flow.returning and client_id != flow.returning.client_id:
        raise SignInFailedError("OpenAI answered for a different registration.")
    with _client() as c:
        reply = _token_reply(c.post(f"{_auth_url()}/api/accounts/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": flow.pkce.verifier,
            "redirect_uri": redirect_uri(),
            "resource": RESOURCE,
        }))
    if PLAN_SCOPE not in str(reply.get("scope", "")).split():
        raise SignInFailedError("ChatGPT plan usage was not granted. Your plan may not support it.")
    if not reply.get("refresh_token") or not reply.get("id_token"):
        raise SignInFailedError("OpenAI's answer was missing a token.")
    claims = verified_claims(reply["id_token"], client_id, flow.pkce.nonce)
    del _flows[flow_id]
    now = time.time()
    return TokenSet(
        client_id=client_id, access_token=reply["access_token"], refresh_token=reply["refresh_token"],
        id_token=reply["id_token"], expires_at=now + float(reply.get("expires_in") or 3600),
        account=claims["sub"], email=claims.get("email"),
    ).refreshed(reply, now)
