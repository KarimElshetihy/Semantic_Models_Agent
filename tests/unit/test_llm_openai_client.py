"""OpenAI-compatible client tests (MOCKED SERVER).

These tests run against a small fake HTTP server on 127.0.0.1 that this file starts itself. It checks
the request the client sends and how it handles replies, errors, redirects, timeouts and oversized
bodies. It is not a language model, and it says nothing about the quality of any model's answers.
"""

import json
import socket
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ssas_agent.llm import ChatMessage, ChatRole, EndpointNotAllowedError, LlmError, LlmSettings, ReplyFormat
from ssas_agent.llm.config import LOOPBACK_HOSTS, MAX_RESPONSE_BYTES
from ssas_agent.llm.openai_compatible import OpenAICompatibleClient

MODEL_NAME = "test-model"
MESSAGES = [ChatMessage(ChatRole.SYSTEM, "be brief"), ChatMessage(ChatRole.USER, "hi")]


def make_reply(text: str, served_model: str = "served-name") -> bytes:
    return json.dumps(
        {"model": served_model, "choices": [{"message": {"role": "assistant", "content": text}}]}
    ).encode("utf-8")


class FakeServerHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.received.append(
            {"path": self.path, "headers": dict(self.headers), "body": body}
        )
        if self.server.delay_seconds:
            time.sleep(self.server.delay_seconds)
        status, headers, reply = self.server.next_reply
        self.send_response(status)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(reply)))
        self.end_headers()
        self.wfile.write(reply)

    def log_message(self, format, *args):
        return


@pytest.fixture
def fake_server():
    """A local fake OpenAI-compatible server (mocked endpoint, not a model)."""
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeServerHandler)
    server.daemon_threads = True
    server.received = []
    server.delay_seconds = 0.0
    server.next_reply = (200, {}, make_reply("hello back"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def base_url(fake_server):
    return f"http://127.0.0.1:{fake_server.server_address[1]}/v1"


def make_settings(base_url, **overrides) -> LlmSettings:
    settings = LlmSettings(
        base_url=base_url,
        model=MODEL_NAME,
        allowed_hosts=LOOPBACK_HOSTS,
        timeout_seconds=5.0,
        temperature=0.0,
        allow_insecure_http=False,
        api_key=None,
    )
    return replace(settings, **overrides)


def test_successful_reply_returns_text_and_counts(fake_server, base_url):
    result = OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)

    assert result.text == "hello back"
    assert result.model == "served-name"
    assert result.endpoint_host == "127.0.0.1"
    assert result.prompt_characters == len("be brief") + len("hi")
    assert result.response_characters == len("hello back")
    assert result.elapsed_seconds >= 0


def test_request_carries_model_messages_temperature_and_no_streaming(fake_server, base_url):
    OpenAICompatibleClient(make_settings(base_url, temperature=0.3)).complete(MESSAGES)

    sent = fake_server.received[0]
    payload = json.loads(sent["body"])
    assert sent["path"] == "/v1/chat/completions"
    assert payload == {
        "model": MODEL_NAME,
        "messages": [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
        "temperature": 0.3,
        "stream": False,
    }


def test_json_object_reply_format_asks_the_server_for_one_json_object(fake_server, base_url):
    OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES, ReplyFormat.JSON_OBJECT)

    payload = json.loads(fake_server.received[0]["body"])
    assert payload["response_format"] == {"type": "json_object"}


def test_text_reply_format_sends_no_response_format(fake_server, base_url):
    OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)

    payload = json.loads(fake_server.received[0]["body"])
    assert "response_format" not in payload


def test_model_name_is_used_when_the_server_does_not_report_one(fake_server, base_url):
    fake_server.next_reply = (200, {}, json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())

    result = OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)

    assert result.model == MODEL_NAME


def test_api_key_is_sent_as_bearer_header_when_configured(fake_server, base_url):
    OpenAICompatibleClient(make_settings(base_url, api_key="secret-key")).complete(MESSAGES)

    assert fake_server.received[0]["headers"]["Authorization"] == "Bearer secret-key"


def test_no_authorization_header_without_a_key(fake_server, base_url):
    OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)

    assert "Authorization" not in fake_server.received[0]["headers"]


def test_http_error_is_reported_without_the_reply_body(fake_server, base_url):
    fake_server.next_reply = (500, {}, b"internal detail that must not leak")

    with pytest.raises(LlmError, match="HTTP 500") as error:
        OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)

    assert "must not leak" not in str(error.value)


def test_api_key_never_appears_in_an_error(fake_server, base_url):
    fake_server.next_reply = (401, {}, b"denied")

    with pytest.raises(LlmError) as error:
        OpenAICompatibleClient(make_settings(base_url, api_key="secret-key")).complete(MESSAGES)

    assert "secret-key" not in str(error.value)


def test_unreachable_endpoint_is_reported():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    closed_port = probe.getsockname()[1]
    probe.close()
    client = OpenAICompatibleClient(make_settings(f"http://127.0.0.1:{closed_port}/v1"))

    with pytest.raises(LlmError, match="could not be reached"):
        client.complete(MESSAGES)


def test_slow_endpoint_times_out(fake_server, base_url):
    fake_server.delay_seconds = 2.0
    client = OpenAICompatibleClient(make_settings(base_url, timeout_seconds=0.2))

    with pytest.raises(LlmError, match="did not answer in time"):
        client.complete(MESSAGES)


def test_environment_proxy_is_ignored(fake_server, base_url, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")

    result = OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)

    assert result.text == "hello back"
    assert len(fake_server.received) == 1


def test_redirect_is_refused_and_the_target_is_not_contacted(fake_server, base_url):
    fake_server.next_reply = (302, {"Location": f"{base_url}/elsewhere"}, b"")

    with pytest.raises(LlmError, match="redirects are refused"):
        OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)

    assert len(fake_server.received) == 1


def test_oversized_reply_is_refused(fake_server, base_url):
    fake_server.next_reply = (200, {}, b"x" * (MAX_RESPONSE_BYTES + 10))

    with pytest.raises(LlmError, match="larger than"):
        OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)


def test_non_json_reply_is_refused(fake_server, base_url):
    fake_server.next_reply = (200, {}, b"<html>not json</html>")

    with pytest.raises(LlmError, match="not valid JSON"):
        OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)


def test_reply_without_choices_is_refused(fake_server, base_url):
    fake_server.next_reply = (200, {}, json.dumps({"model": "x"}).encode())

    with pytest.raises(LlmError, match="no choices"):
        OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)


def test_reply_without_text_content_is_refused(fake_server, base_url):
    fake_server.next_reply = (200, {}, json.dumps({"choices": [{"message": {"content": 5}}]}).encode())

    with pytest.raises(LlmError, match="no text content"):
        OpenAICompatibleClient(make_settings(base_url)).complete(MESSAGES)


def test_remote_endpoint_is_refused_when_the_client_is_created():
    settings = make_settings("https://api.example.com/v1")

    with pytest.raises(EndpointNotAllowedError):
        OpenAICompatibleClient(settings)
