"""MOCK client for tests. It returns scripted replies in order and records what it was sent.

It never talks to a server and is never used by the agent at run time. Tests that use it are
labelled as mocked.
"""

from __future__ import annotations

from collections.abc import Sequence

from ssas_agent.llm.errors import LlmError
from ssas_agent.llm.messages import ChatMessage, CompletionResult, ReplyFormat

SCRIPTED_HOST = "mock"


class ScriptedLlmClient:
    def __init__(self, replies: Sequence[str], model: str = "scripted-mock") -> None:
        self._replies = list(replies)
        self._model = model
        self.calls: list[tuple[ChatMessage, ...]] = []
        self.reply_formats: list[ReplyFormat] = []

    def complete(
        self,
        messages: Sequence[ChatMessage],
        reply_format: ReplyFormat = ReplyFormat.TEXT,
    ) -> CompletionResult:
        self.calls.append(tuple(messages))
        self.reply_formats.append(reply_format)
        if not self._replies:
            raise LlmError("scripted client has no reply left")
        text = self._replies.pop(0)
        return CompletionResult(
            text=text,
            model=self._model,
            endpoint_host=SCRIPTED_HOST,
            prompt_characters=sum(len(message.content) for message in messages),
            response_characters=len(text),
            elapsed_seconds=0.0,
        )
