"""Model draft of the template. The model may fill only what the request states.

Code keeps a draft only if every content word in it also appears in the request. A draft with any new word
is dropped and listed, so an invented value cannot pass silently. This does not catch a word that is
present but placed in the wrong field; that is what the human review is for.
"""

from __future__ import annotations

from collections.abc import Mapping

from ssas_agent.knowledge.retrieve import query_terms
from ssas_agent.llm import ChatMessage, ChatRole, LlmClient, LlmError, ask_structured
from ssas_agent.requirements.fields import FIELD_LABELS, RequirementField

DRAFT_INSTRUCTIONS = (
    "You fill a requirements template for an SSAS Tabular model. "
    "Use only facts stated in the request between the REQUEST markers. "
    "If the request does not state a field, return an empty string for that field. "
    "Never invent business rules, names, numbers or sources. "
    "Reply with one JSON object only, with exactly these keys:"
)


def draft_values(client: LlmClient, request_text: str) -> dict[RequirementField, str]:
    """Ask the model for each field. Raises StructuredOutputError or LlmError on a bad or failed reply."""
    raw = ask_structured(client, _draft_messages(request_text), _draft_schema())
    return {RequirementField(key): value for key, value in raw.items()}


def grounded_drafts(
    drafts: Mapping[RequirementField, str],
    request_text: str,
) -> tuple[dict[RequirementField, str], tuple[RequirementField, ...]]:
    """Return (kept, dropped). Empty drafts are neither kept nor dropped."""
    request_terms = query_terms(request_text)
    kept: dict[RequirementField, str] = {}
    dropped: list[RequirementField] = []
    for field, text in drafts.items():
        cleaned = text.strip()
        if not cleaned:
            continue
        draft_terms = query_terms(cleaned)
        if draft_terms and draft_terms <= request_terms:
            kept[field] = cleaned
        else:
            dropped.append(field)
    return kept, tuple(dropped)


def _draft_schema() -> dict[str, type]:
    return {field.value: str for field in RequirementField}


def _draft_messages(request_text: str) -> list[ChatMessage]:
    field_lines = "\n".join(f"- {field.value}: {FIELD_LABELS[field]}" for field in RequirementField)
    system_text = f"{DRAFT_INSTRUCTIONS}\n{field_lines}"
    user_text = f"<<<REQUEST\n{request_text}\nREQUEST>>>"
    return [ChatMessage(ChatRole.SYSTEM, system_text), ChatMessage(ChatRole.USER, user_text)]
