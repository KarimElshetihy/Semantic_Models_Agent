"""Approve, apply and verify one staged change (step 9).

Approval and apply stay separate calls, so a person can approve in one command and apply in another.
The workflow already refuses to apply when the candidate or the target changed after approval.
After the write, this module checks the file on disk and records the run as VERIFIED or FAILED.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ssas_agent.approval import ApplyOutcome, ApprovalWorkflow, ProposalBinding, State, WorkflowStore
from ssas_agent.approval.proposal import file_sha256
from ssas_agent.audit import RunRecorder, validate_run_id
from ssas_agent.bim.document import BimDocument, InvalidBimError
from ssas_agent.policy import Operation, PathPolicy
from ssas_agent.staging.service import ARTIFACTS_FOLDER, CANDIDATE_FILE, WORKSPACES_FOLDER

WORKFLOW_DATABASE = Path(ARTIFACTS_FOLDER) / "state" / "workflow.sqlite3"


class DeliveryEvent(StrEnum):
    APPROVED = "approved"
    APPLIED = "applied"
    VERIFIED = "verified"
    VERIFICATION_FAILED = "verification_failed"


@dataclass(frozen=True)
class DeliveryResult:
    run_id: str
    outcome: ApplyOutcome
    state: State
    target_path: Path
    verification: dict[str, Any]

    @property
    def verified(self) -> bool:
        return self.state is State.VERIFIED


def open_workflow(policy: PathPolicy) -> ApprovalWorkflow:
    """The approval workflow backed by the project's single workflow database."""
    return ApprovalWorkflow(policy, WorkflowStore(policy, WORKFLOW_DATABASE))


def approve_change(workflow: ApprovalWorkflow, policy: PathPolicy, run_id: str, actor: str) -> ProposalBinding:
    """Record the approval of the submitted proposal, then note it in the run's event log."""
    proposal = workflow.approve(run_id, actor)
    _recorder(policy, run_id).append_event(DeliveryEvent.APPROVED, {"actor": actor, "proposal_id": proposal.proposal_id})
    return proposal


def apply_and_verify(workflow: ApprovalWorkflow, policy: PathPolicy, run_id: str, actor: str) -> DeliveryResult:
    """Write the approved candidate to its approved target, then verify the file on disk."""
    validate_run_id(run_id)
    candidate_path = policy.enforce(Operation.READ, Path(WORKSPACES_FOLDER) / run_id / CANDIDATE_FILE)
    outcome = workflow.apply(run_id, actor, candidate_path)
    binding = workflow.resume(run_id).approved_binding
    recorder = _recorder(policy, run_id)
    recorder.append_event(DeliveryEvent.APPLIED, {"actor": actor, "outcome": outcome.value})
    passed, details = verify_target(binding)
    state = workflow.record_verification(run_id, actor, passed, details)
    event = DeliveryEvent.VERIFIED if passed else DeliveryEvent.VERIFICATION_FAILED
    recorder.append_event(event, {"actor": actor, **details})
    return DeliveryResult(run_id, outcome, state, Path(binding.target_path), details)


def verify_target(binding: ProposalBinding) -> tuple[bool, dict[str, Any]]:
    """The target must hold exactly the approved candidate and must read back as a model."""
    target = Path(binding.target_path)
    actual_sha256 = file_sha256(target)
    hash_matches = actual_sha256 == binding.candidate_sha256
    reads_back = hash_matches and _reads_back_identically(target)
    details = {
        "target_path": binding.target_path,
        "expected_sha256": binding.candidate_sha256,
        "actual_sha256": actual_sha256,
        "hash_matches": hash_matches,
        "reads_back_identically": reads_back,
    }
    return hash_matches and reads_back, details


def _reads_back_identically(target: Path) -> bool:
    try:
        return BimDocument.from_bytes(target.read_bytes()).reproducible_on_load
    except (InvalidBimError, OSError):
        return False


def _recorder(policy: PathPolicy, run_id: str) -> RunRecorder:
    return RunRecorder(policy, Path(ARTIFACTS_FOLDER), run_id)
