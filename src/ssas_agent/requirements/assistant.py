"""Builds a requirements spec. Your entries win over model drafts; anything neither of you gave stays missing.

With no model client, the spec is the blank template plus your entries. A model failure is recorded as a note
on the spec, and the spec is still built.
"""

from __future__ import annotations

from collections.abc import Mapping

from ssas_agent.llm import LlmClient, LlmError
from ssas_agent.requirements.draft import draft_values, grounded_drafts
from ssas_agent.requirements.fields import (
    FieldSource,
    FieldValue,
    RequirementField,
    RequirementSpec,
    RequirementsError,
)

DraftOutcome = tuple[dict[RequirementField, str], tuple[RequirementField, ...], str]


def build_spec(
    request_text: str,
    client: LlmClient | None = None,
    user_values: Mapping[RequirementField, str] | None = None,
) -> RequirementSpec:
    cleaned_request = request_text.strip()
    if not cleaned_request:
        raise RequirementsError("the request is empty")
    entered = {field: text.strip() for field, text in (user_values or {}).items() if text.strip()}
    drafts, dropped, note = _draft_with_model(cleaned_request, client)
    values = {field: _choose_value(field, entered, drafts) for field in RequirementField}
    open_dropped = tuple(field for field in dropped if field not in entered)
    return RequirementSpec(cleaned_request, values, open_dropped, note)


def _choose_value(
    field: RequirementField,
    entered: Mapping[RequirementField, str],
    drafts: Mapping[RequirementField, str],
) -> FieldValue:
    if field in entered:
        return FieldValue(entered[field], FieldSource.USER)
    if field in drafts:
        return FieldValue(drafts[field], FieldSource.DRAFTED_BY_MODEL)
    return FieldValue("", FieldSource.MISSING)


def _draft_with_model(request_text: str, client: LlmClient | None) -> DraftOutcome:
    if client is None:
        return {}, (), ""
    try:
        raw_drafts = draft_values(client, request_text)
    except LlmError as error:
        return {}, (), f"model draft unavailable: {error}"
    kept, dropped = grounded_drafts(raw_drafts, request_text)
    return kept, dropped, ""
