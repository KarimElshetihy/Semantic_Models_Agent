"""Structured replies: a model answer must be one JSON object with the typed fields the caller asks for.

Anything else is refused: prose around the JSON, a list, a missing field, or a field of the wrong type.
The refusal is recorded (when a recorder is given) without the reply text, so a bad answer never
leaks into the audit trail.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from ssas_agent.audit import RunRecorder
from ssas_agent.llm.client import LlmClient
from ssas_agent.llm.errors import LlmError
from ssas_agent.llm.messages import ChatMessage

_SINGLE_FENCE = re.compile(r"\A```(?:(?i:json))?[ \t]*\r?\n(.*?)\r?\n?```\Z", re.DOTALL)


class StructuredEvent(StrEnum):
    REPLY_REFUSED = "llm_reply_refused"


class StructuredOutputError(LlmError):
    """The reply is not the JSON object that was asked for. The message says why, never what the reply said."""


def parse_object(reply_text: str) -> dict[str, Any]:
    stripped = reply_text.strip()
    fenced = _SINGLE_FENCE.match(stripped)
    candidate = fenced.group(1) if fenced else stripped
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        raise StructuredOutputError("reply is not a single valid JSON object") from None
    if not isinstance(value, dict):
        raise StructuredOutputError("reply is not a JSON object")
    return value


def check_fields(value: Mapping[str, Any], schema: Mapping[str, type]) -> dict[str, Any]:
    """Return only the schema fields, after checking that each is present and has the right type."""
    checked: dict[str, Any] = {}
    for name, expected_type in schema.items():
        if name not in value:
            raise StructuredOutputError(f"reply is missing field '{name}'")
        if not _matches_type(value[name], expected_type):
            raise StructuredOutputError(f"field '{name}' must be {expected_type.__name__}")
        checked[name] = value[name]
    return checked


def ask_structured(
    client: LlmClient,
    messages: Sequence[ChatMessage],
    schema: Mapping[str, type],
    recorder: RunRecorder | None = None,
) -> dict[str, Any]:
    """Send the messages and return the checked fields. Raises StructuredOutputError for a bad reply."""
    result = client.complete(messages)
    try:
        return check_fields(parse_object(result.text), schema)
    except StructuredOutputError as error:
        if recorder is not None:
            recorder.append_event(
                StructuredEvent.REPLY_REFUSED,
                {"reason": str(error), "model": result.model, "response_characters": result.response_characters},
            )
        raise


def _matches_type(value: Any, expected_type: type) -> bool:
    if expected_type is int and isinstance(value, bool):
        return False
    return isinstance(value, expected_type)
