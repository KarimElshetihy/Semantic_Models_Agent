"""The two positive steps of the exit gate: a new sample model, and a safe edit to an existing model.

The new model is built and checked in workspaces/ only. The edit is staged from a read-only model, approved by a
person typing the approval word, applied to the named destination, and verified on disk.
"""

from __future__ import annotations

from pathlib import Path

from ssas_agent.approval import ApprovalWorkflow
from ssas_agent.bim.document import BimDocument, sha256_hex
from ssas_agent.delivery import apply_and_verify
from ssas_agent.delivery.prompts import ReadLine, WriteLine, request_approval
from ssas_agent.demo.records import EditOutcome, NewModelOutcome
from ssas_agent.edit import replace_measure_expression
from ssas_agent.newmodel import create_new_model, parse_spec_text
from ssas_agent.policy import PathPolicy
from ssas_agent.staging import ChangeStager
from ssas_agent.validation import run_static_checks
from ssas_agent.validation.findings import ERROR, WARNING

EXISTING_MODEL_PATH = Path("tests") / "fixtures" / "RETA_MODEL" / "Model.bim"
EDIT_TABLE = "TRX"
EDIT_MEASURE = "_TRX_AMOUNT"
EDIT_EXPRESSION = "SUM ( 'TRX'[AMOUNT] ) + 0"
EDIT_OPERATION = "replace measure expression"
STAGING_ACTOR = "agent:exit-gate-demo"
NOT_APPROVED_MESSAGE = "the edit was not approved; nothing was written to the destination"


class ApprovalNotGivenError(RuntimeError):
    """Raised when the person does not type the approval word. The demo stops there."""


def build_sample_model(policy: PathPolicy, spec_text: str, run_id: str) -> NewModelOutcome:
    """Build the sample model into workspaces/ and check it. Refused specs or models write nothing."""
    spec = parse_spec_text(spec_text)
    candidate = create_new_model(policy, spec, run_id)
    report = run_static_checks(BimDocument.from_bytes(candidate.model_path.read_bytes()).data)
    counts = report.count_by_severity()
    return NewModelOutcome(
        run_id=run_id,
        project_name=spec.project_name,
        model_path=_display(policy, candidate.model_path),
        project_path=_display(policy, candidate.project_path),
        mapping_path=_display(policy, candidate.mapping_path),
        model_sha256=_sha256_of(candidate.model_path),
        errors=counts[ERROR],
        warnings=counts[WARNING],
        not_checked=tuple(f"{item.identity}: {item.reason}" for item in report.not_checked),
    )


def run_safe_edit(
    policy: PathPolicy,
    workflow: ApprovalWorkflow,
    run_id: str,
    approver: str,
    read_line: ReadLine,
    write_line: WriteLine,
) -> EditOutcome:
    """Stage one measure change, ask the person to approve it, then apply and verify it at the destination."""
    stager = ChangeStager(policy, workflow)
    staged = stager.stage(
        run_id,
        STAGING_ACTOR,
        EXISTING_MODEL_PATH,
        edit_measure,
        EDIT_OPERATION,
        target_model=policy.apply_target,
    )
    if not request_approval(workflow, policy, run_id, approver, read_line, write_line):
        raise ApprovalNotGivenError(NOT_APPROVED_MESSAGE)
    result = apply_and_verify(workflow, policy, run_id, approver)
    return EditOutcome(
        run_id=run_id,
        source_path=EXISTING_MODEL_PATH.as_posix(),
        target_path=_display(policy, result.target_path),
        candidate_sha256=staged.proposal.candidate_sha256,
        change_summary=dict(staged.change_summary),
        category_summary=dict(staged.category_summary),
        staged_by=STAGING_ACTOR,
        approved_by=approver,
        outcome=result.outcome.value,
        state=result.state.value,
        verified=result.verified,
        verification=dict(result.verification),
    )


def edit_measure(document: BimDocument) -> BimDocument:
    """The one change the demo makes: the expression of one existing measure."""
    return replace_measure_expression(document, EDIT_TABLE, EDIT_MEASURE, EDIT_EXPRESSION)


def _sha256_of(path: Path) -> str:
    return sha256_hex(path.read_bytes())


def _display(policy: PathPolicy, path: Path) -> str:
    try:
        return path.resolve().relative_to(policy.project_root.resolve()).as_posix()
    except ValueError:
        return str(path)
