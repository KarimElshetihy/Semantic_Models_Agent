"""Structured reply tests. Replies come from ScriptedLlmClient (MOCK), so no model or server is involved."""

import json

import pytest

from ssas_agent.audit import RunRecorder
from ssas_agent.llm import ChatMessage, LlmError, ScriptedLlmClient, StructuredOutputError
from ssas_agent.policy import PathPolicy
from ssas_agent.llm.structured import REFUSED_EVENT, ask_structured, check_fields, parse_object

SCHEMA = {"name": str, "count": int}
MESSAGES = [ChatMessage("user", "give me a name and a count")]
SECRET_REPLY = "SECRET_REPLY_TEXT"


def test_plain_json_object_is_parsed():
    assert parse_object('{"name": "Sales", "count": 2}') == {"name": "Sales", "count": 2}


@pytest.mark.parametrize("fence", ["```json", "```", "```JSON"])
def test_single_fenced_block_is_accepted(fence):
    reply = f'{fence}\n{{"name": "Sales", "count": 2}}\n```'

    assert parse_object(reply) == {"name": "Sales", "count": 2}


@pytest.mark.parametrize(
    "reply, reason",
    [
        ('Sure! {"name": "Sales", "count": 2}', "not a single valid JSON object"),
        ('{"name": "a"}{"name": "b"}', "not a single valid JSON object"),
        ("[1, 2, 3]", "not a JSON object"),
        ("", "not a single valid JSON object"),
    ],
)
def test_reply_that_is_not_one_json_object_is_refused(reply, reason):
    with pytest.raises(StructuredOutputError, match=reason):
        parse_object(reply)


def test_missing_field_is_refused():
    with pytest.raises(StructuredOutputError, match="missing field 'count'"):
        check_fields({"name": "Sales"}, SCHEMA)


def test_wrong_type_is_refused():
    with pytest.raises(StructuredOutputError, match="field 'name' must be str"):
        check_fields({"name": 3, "count": 2}, SCHEMA)


def test_boolean_is_not_accepted_as_an_integer():
    with pytest.raises(StructuredOutputError, match="field 'count' must be int"):
        check_fields({"name": "Sales", "count": True}, SCHEMA)


def test_extra_fields_are_dropped():
    checked = check_fields({"name": "Sales", "count": 2, "note": "extra"}, SCHEMA)

    assert checked == {"name": "Sales", "count": 2}


def test_ask_structured_returns_checked_fields_and_sends_the_messages():
    client = ScriptedLlmClient(['{"name": "Sales", "count": 2}'])

    fields = ask_structured(client, MESSAGES, SCHEMA)

    assert fields == {"name": "Sales", "count": 2}
    assert client.calls == [tuple(MESSAGES)]


def test_refused_reply_is_recorded_without_the_reply_text(tmp_path):
    recorder = RunRecorder(PathPolicy(tmp_path), tmp_path / "artifacts", "run-refused")
    client = ScriptedLlmClient([json.dumps({"name": "Sales", "note": SECRET_REPLY})])

    with pytest.raises(StructuredOutputError):
        ask_structured(client, MESSAGES, SCHEMA, recorder=recorder)

    events_text = (tmp_path / "artifacts" / "run-refused" / "events.jsonl").read_text(encoding="utf-8")
    events = [json.loads(line) for line in events_text.splitlines()]
    refused = [event for event in events if event.get("event") == REFUSED_EVENT]
    assert len(refused) == 1
    assert "missing field 'count'" in refused[0]["reason"]
    assert SECRET_REPLY not in events_text


def test_client_failure_is_not_hidden_by_the_structured_layer():
    client = ScriptedLlmClient([])

    with pytest.raises(LlmError, match="no reply left"):
        ask_structured(client, MESSAGES, SCHEMA)
