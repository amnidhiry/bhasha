"""Model providers behind one call: complete_json(system, user, schema) -> dict.

- ChatGPTPlanProvider: OpenAI Responses API with a "Sign in with ChatGPT" token
  (plan usage, no API key). The plan refuses some request fields; see
  REFUSED_FIELDS. Request shape follows SurfSense (Apache-2.0).
- OpenAICompatibleProvider: /chat/completions on LM Studio, or any
  OpenAI-compatible endpoint with an API key.
- FakeProvider: scripted replies for tests.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from app.llm.errors import LlmError, PlanLimitError, SignInRequiredError

# Tests swap this for an httpx.MockTransport.
transport: httpx.BaseTransport | None = None

# What the plan's Responses endpoint rejects (SIWC preview limitations).
REFUSED_FIELDS = frozenset({
    "background", "conversation", "max_output_tokens", "max_tool_calls", "metadata", "moderation",
    "multi_agent", "previous_response_id", "prompt", "prompt_cache_retention", "safety_identifier",
    "temperature", "top_logprobs", "top_p", "truncation", "user",
})
USAGE_LIMIT = "subscription_sharing_usage_limit_exceeded"
INVALID_USER = "subscription_sharing_invalid_user"


@dataclass
class Completion:
    data: dict
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0


def _client(headers: dict, timeout: float = 180.0) -> httpx.Client:
    return httpx.Client(headers=headers, timeout=httpx.Timeout(timeout, connect=10.0), transport=transport)


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise LlmError("The model's reply was not valid JSON.") from error
    if not isinstance(data, dict):
        raise LlmError("The model's reply was not a JSON object.")
    return data


def _error_fields(payload: object) -> tuple[str | None, str]:
    if not isinstance(payload, dict):
        return None, "the model failed"
    err = payload.get("error")
    if isinstance(err, dict):
        return err.get("code"), str(err.get("message") or "the model failed")[:400]
    return None, str(payload.get("detail") or "the model failed")[:400]


class ChatGPTPlanProvider:
    kind = "chatgpt"

    def __init__(self, base_url: str, access_token: Callable[[bool], str]):
        """access_token(force_refresh) returns a usable bearer token."""
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token

    def models(self) -> list[dict]:
        with _client({"Authorization": f"Bearer {self.access_token(False)}"}, 30) as c:
            reply = c.get(f"{self.base_url}/models")
        if reply.status_code == 401:
            raise SignInRequiredError()
        reply.raise_for_status()
        entries = reply.json().get("models", [])
        return [
            {"id": e["slug"], "name": e.get("display_name") or e["slug"], "context_window": e.get("context_window")}
            for e in entries if isinstance(e, dict) and isinstance(e.get("slug"), str) and e.get("visibility") == "list"
        ]

    def complete_json(self, model: str, system: str, user: str, schema: dict, cache_key: str | None = None) -> Completion:
        body: dict = {
            "model": model,
            # The plan rejects `system` items; a developer turn ranks the same.
            "input": [{"role": "developer", "content": system}, {"role": "user", "content": user}],
            "store": False,
            "stream": True,
            "text": {"format": {"type": "json_schema", "name": "response", "schema": schema}},
        }
        if cache_key:
            body["prompt_cache_key"] = cache_key  # allowed; prompt_cache_retention is not
        body = {k: v for k, v in body.items() if k not in REFUSED_FIELDS}
        for attempt in range(2):
            with _client({"Authorization": f"Bearer {self.access_token(attempt > 0)}"}) as c:
                with c.stream("POST", f"{self.base_url}/responses", json=body) as reply:
                    if reply.status_code == 401 and attempt == 0:
                        continue  # refresh the token once
                    if reply.status_code >= 400:
                        reply.read()
                        try:
                            code, message = _error_fields(reply.json())
                        except ValueError:
                            code, message = None, f"HTTP {reply.status_code}"
                        if code == USAGE_LIMIT or reply.status_code == 429:
                            raise PlanLimitError()
                        if code == INVALID_USER or reply.status_code == 401:
                            raise SignInRequiredError()
                        raise LlmError(f"The model refused the request: {message}")
                    return self._read_stream(reply, model)
        raise SignInRequiredError()

    @staticmethod
    def _read_stream(reply: httpx.Response, model: str) -> Completion:
        """Text deltas until response.completed; anything else ending the stream is a failure."""
        parts: list[str] = []
        for line in reply.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            event = json.loads(payload)
            kind = event.get("type")
            if kind == "response.output_text.delta":
                parts.append(event.get("delta") or "")
            elif kind == "response.completed":
                resp = event.get("response") or {}
                usage = resp.get("usage") or {}
                text = "".join(parts)
                if not text:  # some servers only put text in the final object
                    for item in resp.get("output") or []:
                        for content in item.get("content") or []:
                            if content.get("type") == "output_text":
                                text += content.get("text", "")
                return Completion(
                    data=_parse_json(text), model=resp.get("model") or model,
                    input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
                    cached_tokens=(usage.get("input_tokens_details") or {}).get("cached_tokens", 0),
                )
            elif kind in ("response.failed", "error"):
                code, message = _error_fields((event.get("response") or event))
                if code == USAGE_LIMIT:
                    raise PlanLimitError()
                raise LlmError(f"The model failed: {message}")
            elif kind == "response.incomplete":
                raise LlmError("The model stopped before finishing its reply.")
        raise LlmError("The reply ended before the model finished it.")


class OpenAICompatibleProvider:
    """LM Studio (http://host:1234/v1, no key) or any OpenAI-compatible API with a key."""

    kind = "openai_compatible"

    def __init__(self, base_url: str, api_key: str | None):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    def models(self) -> list[dict]:
        with _client(self.headers, 30) as c:
            reply = c.get(f"{self.base_url}/models").raise_for_status()
        return [{"id": m["id"], "name": m["id"], "context_window": None} for m in reply.json().get("data", [])]

    def complete_json(self, model: str, system: str, user: str, schema: dict, cache_key: str | None = None) -> Completion:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "response", "schema": schema}},
        }
        with _client(self.headers) as c:
            reply = c.post(f"{self.base_url}/chat/completions", json=body)
        if reply.status_code == 429:
            raise PlanLimitError("The model server is rate-limiting requests. Try again shortly.")
        if reply.status_code >= 400:
            raise LlmError(f"The model server refused the request: {_error_fields(reply.json())[1]}")
        payload = reply.json()
        usage = payload.get("usage") or {}
        return Completion(
            data=_parse_json(payload["choices"][0]["message"]["content"] or ""), model=payload.get("model") or model,
            input_tokens=usage.get("prompt_tokens", 0), output_tokens=usage.get("completion_tokens", 0),
        )


@dataclass
class FakeProvider:
    """Scripted replies for tests: each call pops the next dict (or calls it with the prompt)."""

    replies: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    kind: str = "fake"

    def models(self) -> list[dict]:
        return [{"id": "fake-model", "name": "Fake", "context_window": 100_000}]

    def complete_json(self, model: str, system: str, user: str, schema: dict, cache_key: str | None = None) -> Completion:
        self.calls.append({"system": system, "user": user, "schema": schema})
        reply = self.replies.pop(0)
        data = reply(user) if callable(reply) else reply
        return Completion(data=data, model=model, input_tokens=len(system) + len(user), output_tokens=100)
