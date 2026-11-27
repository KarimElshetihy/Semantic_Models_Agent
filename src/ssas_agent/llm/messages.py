"""Plain data for LLM requests and replies. Usage figures are counts only; prompt and reply text
are kept by the caller, not logged here."""

from __future__ import annotations

from dataclasses import dataclass

ROLES = ("system", "user", "assistant")


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"role must be one of {ROLES}, got {self.role!r}")
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
