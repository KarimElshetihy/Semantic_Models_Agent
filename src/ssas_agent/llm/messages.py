"""Plain data for LLM requests and replies. Usage figures are counts only; prompt and reply text
are kept by the caller, not logged here."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ChatRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True)
class ChatMessage:
    role: ChatRole
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, ChatRole):
            raise ValueError(f"role must be a ChatRole member, got {self.role!r}")
        if not isinstance(self.content, str):
            raise ValueError("message content must be text")


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str
    endpoint_host: str
    prompt_characters: int
    response_characters: int
    elapsed_seconds: float
