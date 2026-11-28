"""Phase 1 exit gate (requirements section 12): a new sample model, a safe edit to an existing model, and refusals.

Order: the new model is built first. Then the edit is staged, approved by a person typing the approval word, applied
to the named destination and verified. Then the unsafe requests are tried. The report is written last, whatever
happened, so a stopped run still leaves a record.
"""

from __future__ import annotations

from pathlib import Path

from ssas_agent.approval import ApprovalError, ApprovalWorkflow
from ssas_agent.audit import InvalidRunIdError, new_run_id, validate_run_id
from ssas_agent.delivery import open_workflow
from ssas_agent.delivery.prompts import ReadLine, WriteLine
from ssas_agent.demo.records import EditOutcome, ExitGateResult, NewModelOutcome
from ssas_agent.demo.refusals import run_refusals
from ssas_agent.demo.report import report_location, write_exit_gate_report
from ssas_agent.demo.steps import ApprovalNotGivenError, build_sample_model, run_safe_edit
from ssas_agent.edit import MeasureEditError
from ssas_agent.newmodel import NewModelError, SpecError, read_spec_file
from ssas_agent.policy import PathPolicy
from ssas_agent.staging import ChangeStager, StagingError

SAMPLE_SPEC_PATH = Path("specs") / "SAMPLE_SALES.json"
DESTINATION_FILE_NAME = "Model.bim"
STOP_ERRORS = (
    NewModelError,
    SpecError,
    StagingError,
    ApprovalError,
    ApprovalNotGivenError,
    MeasureEditError,
    InvalidRunIdError,
)


class DemoRefusedError(RuntimeError):
    """The demo does not start: no destination is named, or the destination already holds a model."""


def run_exit_gate(
    policy: PathPolicy,
    *,
    approver: str,
    run_prefix: str | None,
    read_line: ReadLine,
    write_line: WriteLine,
) -> ExitGateResult:
    destination = _ready_destination(policy)
    prefix = validate_run_id(run_prefix or new_run_id())
    workflow = open_workflow(policy)
    spec_text = read_spec_file(policy, SAMPLE_SPEC_PATH)
    new_model, edit, stopped_reason = _positive_steps(
        policy, workflow, spec_text, prefix, approver, read_line, write_line
    )
    write_line("Part 3: refusals (nothing may be written)")
    refusals, refusals_wrote_nothing = run_refusals(
        policy, ChangeStager(policy, workflow), spec_text, prefix, destination
    )
    result = ExitGateResult(
        run_prefix=prefix,
        new_model=new_model,
        edit=edit,
        refusals=refusals,
        refusals_wrote_nothing=refusals_wrote_nothing,
        stopped_reason=stopped_reason,
    )
    write_exit_gate_report(policy, result)
    write_line(f"Report written: {report_location(prefix)}")
    return result


def _positive_steps(
    policy: PathPolicy,
    workflow: ApprovalWorkflow,
    spec_text: str,
    prefix: str,
    approver: str,
    read_line: ReadLine,
    write_line: WriteLine,
) -> tuple[NewModelOutcome | None, EditOutcome | None, str | None]:
    write_line("Part 1: new sample model (checked in workspaces/ only)")
    try:
        new_model = build_sample_model(policy, spec_text, f"{prefix}-model")
    except STOP_ERRORS as error:
        return None, None, f"the new sample model was refused: {error}"
    write_line("Part 2: safe edit to an existing model (you approve by typing the approval word)")
    try:
        edit = run_safe_edit(policy, workflow, f"{prefix}-edit", approver, read_line, write_line)
    except STOP_ERRORS as error:
        return new_model, None, str(error)
    return new_model, edit, None


def _ready_destination(policy: PathPolicy) -> Path:
    if policy.apply_target is None:
        raise DemoRefusedError("the demo needs a named destination folder (--apply-folder)")
    if policy.apply_target.exists():
        raise DemoRefusedError(
            f"{DESTINATION_FILE_NAME} already exists at {policy.apply_target}. The demo never overwrites it; "
            "move or delete that file to run the demo again."
        )
    return policy.apply_target
