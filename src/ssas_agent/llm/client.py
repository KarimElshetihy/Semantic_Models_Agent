"""The one interface the rest of the agent uses to talk to a model. Any provider implements this."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from ssas_agent.llm.messages import ChatMessage, CompletionResult, ReplyFormat


class LlmClient(Protocol):
    def complete(
        self,
        messages: Sequence[ChatMessage],
        reply_format: ReplyFormat = ReplyFormat.TEXT,
    ) -> CompletionResult:
        """Send the conversation and return the model's text. Raises LlmError on any failure."""
        ...
