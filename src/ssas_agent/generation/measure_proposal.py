"""Proposes a new DAX measure for a model.

Flow: the model drafts table, name and expression from the request. The code applies the edit in memory,
runs the static checks, and refuses if the new measure adds an error or cannot be checked. Only then is the
change staged for approval. Nothing is written to a model here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ssas_agent.bim.document import BimDocument
from ssas_agent.edit import MeasureEditError, add_measure
from ssas_agent.generation.context import model_context
from ssas_agent.generation.errors import CandidateRefusedError, GenerationError
from ssas_agent.llm import ChatMessage, ChatRole, LlmClient, StructuredOutputError, ask_structured
from ssas_agent.policy import Operation, PathPolicy
from ssas_agent.staging import ChangeStager, StagedChange
from ssas_agent.validation import run_static_checks
from ssas_agent.validation.findings import ERROR, CheckReport
from ssas_agent.validation.model_index import measure_id

DRAFT_INSTRUCTIONS = (
    "You write one DAX measure for an SSAS Tabular model. "
    "Use only the tables, columns and measures listed in MODEL CONTEXT. "
    "Reply with one JSON object only, with exactly these keys: table, measure_name, expression. "
    "The expression is the DAX formula only, without the measure name and without '='."
)
DRAFT_SCHEMA: dict[str, type] = {"table": str, "measure_name": str, "expression": str}
MAX_DRAFT_ATTEMPTS = 3


@dataclass(frozen=True)
class MeasureProposal:
    table_name: str
    measure_name: str
    expression: str


def draft_measure(client: LlmClient, request_text: str, data: dict[str, Any]) -> MeasureProposal:
    """Ask the model for one measure, retrying a bad reply up to MAX_DRAFT_ATTEMPTS times.

    Raises GenerationError if no valid reply arrives, or LlmError if the model cannot be reached.
    """
    messages = _draft_messages(request_text, data)
    last_refusal = ""
    for _attempt in range(MAX_DRAFT_ATTEMPTS):
        try:
            fields = ask_structured(client, messages, DRAFT_SCHEMA)
        except StructuredOutputError as error:
            last_refusal = str(error)
            continue
        return _checked_proposal(fields)
    raise GenerationError(f"no valid draft after {MAX_DRAFT_ATTEMPTS} attempts: {last_refusal}")


def propose_measure(
    stager: ChangeStager,
    policy: PathPolicy,
    source_model: Path,
    run_id: str,
    actor: str,
    proposal: MeasureProposal,
) -> StagedChange:
    """Check the candidate in memory, then stage it. Raises CandidateRefusedError if the checks fail."""
    base_document = _read_base(policy, source_model)
    edit = _edit_for(proposal)
    candidate = _apply_or_refuse(edit, base_document)
    reasons = _blocking_reasons(base_document.data, candidate.data, proposal)
    if reasons:
        raise CandidateRefusedError(tuple(reasons))
    operation_name = f"add measure {proposal.table_name}/{proposal.measure_name}"
    return stager.stage(run_id, actor, source_model, edit, operation_name)


def _draft_messages(request_text: str, data: dict[str, Any]) -> list[ChatMessage]:
    system_text = f"{DRAFT_INSTRUCTIONS}\n\nMODEL CONTEXT:\n{model_context(data)}"
    user_text = f"<<<REQUEST\n{request_text}\nREQUEST>>>"
    return [ChatMessage(ChatRole.SYSTEM, system_text), ChatMessage(ChatRole.USER, user_text)]


def _checked_proposal(fields: dict[str, Any]) -> MeasureProposal:
    proposal = MeasureProposal(
        table_name=fields["table"].strip(),
        measure_name=fields["measure_name"].strip(),
        expression=fields["expression"].strip(),
    )
    missing = [label for label, value in (
        ("table", proposal.table_name),
        ("measure name", proposal.measure_name),
        ("expression", proposal.expression),
    ) if not value]
    if missing:
        raise CandidateRefusedError((f"the draft has no {', '.join(missing)}",))
    return proposal


def _read_base(policy: PathPolicy, source_model: Path) -> BimDocument:
    source_path = policy.enforce(Operation.READ, source_model)
    return BimDocument.from_bytes(source_path.read_bytes())


def _edit_for(proposal: MeasureProposal) -> Callable[[BimDocument], BimDocument]:
    def edit(document: BimDocument) -> BimDocument:
        return add_measure(document, proposal.table_name, proposal.measure_name, proposal.expression)

    return edit


def _apply_or_refuse(edit: Callable[[BimDocument], BimDocument], base: BimDocument) -> BimDocument:
    try:
        return edit(base)
    except MeasureEditError as error:
        raise CandidateRefusedError((str(error),)) from None


def _blocking_reasons(base_data: dict[str, Any], candidate_data: dict[str, Any], proposal: MeasureProposal) -> list[str]:
    base_report = run_static_checks(base_data)
    candidate_report = run_static_checks(candidate_data)
    return [
        *_new_error_reasons(base_report, candidate_report),
        *_unchecked_reasons(candidate_report, proposal),
    ]


def _new_error_reasons(base_report: CheckReport, candidate_report: CheckReport) -> list[str]:
    known = {(finding.rule_id, finding.identity) for finding in base_report.findings if finding.severity == ERROR}
    return [
        f"{finding.rule_id} at {finding.identity}: {finding.evidence}"
        for finding in candidate_report.findings
        if finding.severity == ERROR and (finding.rule_id, finding.identity) not in known
    ]


def _unchecked_reasons(report: CheckReport, proposal: MeasureProposal) -> list[str]:
    new_identity = measure_id(proposal.table_name, proposal.measure_name)
    return [
        f"not checked, so not staged: {item.identity} ({item.reason})"
        for item in report.not_checked
        if item.identity == new_identity
    ]
