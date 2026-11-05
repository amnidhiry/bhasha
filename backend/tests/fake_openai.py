"""A fake auth.openai.com + api.openai.com for the Sign in with ChatGPT flow."""

import base64
import json
import time
from urllib.parse import parse_qs

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

AUTH = "https://auth.openai.com"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
CLIENT_ID = "client_registered_123"


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def id_token(nonce: str, client_id: str = CLIENT_ID, iss: str = AUTH) -> str:
    header = b64(json.dumps({"alg": "RS256", "kid": "k1"}).encode())
    claims = b64(json.dumps({"iss": iss, "aud": client_id, "sub": "user-abc", "email": "abe@example.com",
                             "exp": time.time() + 3600, "nonce": nonce}).encode())
    sig = KEY.sign(f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{header}.{claims}.{b64(sig)}"


def jwks() -> dict:
    n = KEY.public_key().public_numbers()
    to_b = lambda i: i.to_bytes((i.bit_length() + 7) // 8, "big")
    return {"keys": [{"kty": "RSA", "kid": "k1", "n": b64(to_b(n.n)), "e": b64(to_b(n.e))}]}


class FakeOpenAI:
    def __init__(self, scope: str = "openid offline_access chatgpt.tokens.use.direct"):
        self.scope = scope
        self.nonce = None
        self.requests: list[httpx.Request] = []
        self.refreshes = 0
        self.stream_events: list[dict] | None = None
        self.responses_status = 200
        self.responses_error: dict | None = None
        self.unauthorized_once = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/.well-known/jwks.json":
            return httpx.Response(200, json=jwks())
        if path == "/api/accounts/oauth/token":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            if form["grant_type"] == "refresh_token":
                self.refreshes += 1
                return httpx.Response(200, json={"access_token": f"access-{self.refreshes + 1}", "expires_in": 3600})
            return httpx.Response(200, json={
                "access_token": "access-1", "refresh_token": "refresh-1", "expires_in": 3600, "scope": self.scope,
                "id_token": id_token(self.nonce, form["client_id"]),
            })
        if path == "/api/accounts/oauth/revoke":
            return httpx.Response(200)
        if path == "/v1/models":
            return httpx.Response(200, json={"models": [
                {"slug": "gpt-plan-main", "display_name": "Main", "visibility": "list", "context_window": 200000},
                {"slug": "hidden", "visibility": "hide"},
            ]})
        if path == "/v1/responses":
            if self.unauthorized_once:
                self.unauthorized_once = False
                return httpx.Response(401, json={"error": {"message": "expired"}})
            if self.responses_status != 200:
                return httpx.Response(self.responses_status, json=self.responses_error or {})
            lines = "".join(f"data: {json.dumps(e)}\n\n" for e in (self.stream_events or []))
            return httpx.Response(200, text=lines, headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def text_events(text: str, usage: dict | None = None) -> list[dict]:
    half = len(text) // 2
    return [
        {"type": "response.created"},
        {"type": "response.output_text.delta", "delta": text[:half]},
        {"type": "response.output_text.delta", "delta": text[half:]},
        {"type": "response.completed", "response": {"model": "gpt-plan-main",
                                                    "usage": usage or {"input_tokens": 1200, "output_tokens": 300,
                                                                       "input_tokens_details": {"cached_tokens": 1000}}}},
    ]
