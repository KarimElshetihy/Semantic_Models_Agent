"""Client for any server that speaks the OpenAI chat completions API (local servers included).

Safety measures:
- The endpoint policy is checked when the client is created, so a refused endpoint never sends anything.
- Redirects are refused, so a prompt cannot move to another host.
- The reply size is capped, and the request has a timeout.
- The API key is sent only as a bearer header and is never part of an error message.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Sequence
from typing import IO, Any
from urllib.error import HTTPError, URLError

from ssas_agent.llm.config import MAX_RESPONSE_BYTES, LlmSettings
from ssas_agent.llm.endpoint import check_endpoint
from ssas_agent.llm.errors import LlmError
from ssas_agent.llm.messages import ChatMessage, CompletionResult, ReplyFormat

CHAT_PATH = "/chat/completions"


class _NoEnvironmentProxy(urllib.request.ProxyHandler):
    """Ignore HTTP_PROXY-style variables: a proxy would receive prompts without passing the endpoint policy."""

    def __init__(self) -> None:
        super().__init__({})


class _RefuseRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LlmError(f"endpoint answered with a redirect ({code}); redirects are refused")


class OpenAICompatibleClient:
    def __init__(self, settings: LlmSettings, opener: urllib.request.OpenerDirector | None = None) -> None:
        decision = check_endpoint(settings.base_url, settings.allowed_hosts, settings.allow_insecure_http)
        self._host = decision.host
        self._settings = settings
        self._url = settings.base_url.rstrip("/") + CHAT_PATH
        self._opener = opener or urllib.request.build_opener(_NoEnvironmentProxy(), _RefuseRedirects)

    def complete(
        self,
        messages: Sequence[ChatMessage],
        reply_format: ReplyFormat = ReplyFormat.TEXT,
    ) -> CompletionResult:
        body = json.dumps(self._payload(messages, reply_format), ensure_ascii=False).encode("utf-8")
        started = time.monotonic()
        raw = self._post(body)
        elapsed = time.monotonic() - started
        text, reported_model = _reply_text_and_model(raw)
        return CompletionResult(
            text=text,
            model=reported_model or self._settings.model,
            endpoint_host=self._host,
            prompt_characters=sum(len(message.content) for message in messages),
            response_characters=len(text),
            elapsed_seconds=round(elapsed, 3),
        )

    def _payload(self, messages: Sequence[ChatMessage], reply_format: ReplyFormat) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [{"role": message.role.value, "content": message.content} for message in messages],
            "temperature": self._settings.temperature,
            "stream": False,
        }
        if reply_format is ReplyFormat.JSON_OBJECT:
            payload["response_format"] = {"type": ReplyFormat.JSON_OBJECT.value}
        return payload

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._settings.api_key:
            headers["Authorization"] = f"Bearer {self._settings.api_key}"
        return headers

    def _post(self, body: bytes) -> bytes:
        request = urllib.request.Request(self._url, data=body, method="POST", headers=self._headers())
        try:
            with self._opener.open(request, timeout=self._settings.timeout_seconds) as response:
                return _read_limited(response)
        except HTTPError as error:
            raise LlmError(f"endpoint answered HTTP {error.code}") from None
        except (URLError, TimeoutError, OSError):
            raise LlmError("endpoint could not be reached or did not answer in time") from None


def _read_limited(response: IO[bytes]) -> bytes:
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise LlmError(f"endpoint reply is larger than {MAX_RESPONSE_BYTES} bytes")
    return data


def _reply_text_and_model(raw: bytes) -> tuple[str, str | None]:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise LlmError("endpoint reply is not valid JSON") from None
    choices = document.get("choices") if isinstance(document, dict) else None
    if not isinstance(choices, list) or not choices:
        raise LlmError("endpoint reply has no choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LlmError("endpoint reply has no text content")
    reported_model = document.get("model")
    return content, reported_model if isinstance(reported_model, str) else None
