"""Approval workflow: the only way to change a run's state.

Applying a candidate requires an approval whose facts still match the files on disk.
Every refused operation is recorded as an attempt before the error is raised.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ssas_agent.approval.errors import ApprovalError, ApprovalRequiredError, StaleApprovalError
from ssas_agent.approval.proposal import ProposalBinding, file_sha256, sha256_of_value
from ssas_agent.approval.states import Action, State, next_state
from ssas_agent.approval.store import WorkflowStore
from ssas_agent.audit.run_ids import validate_run_id
from ssas_agent.bim.document import sha256_hex
from ssas_agent.bim.storage import write_bytes_atomically
from ssas_agent.policy import Operation, PathPolicy, PolicyDeniedError

APPROVAL_HOLDING_STATES = frozenset({State.APPROVED, State.APPLIED, State.VERIFIED, State.FAILED})
REFUSED_OUTCOME = "refused"


class ApplyOutcome(str, Enum):
    WRITTEN = "written"
    ALREADY_IN_PLACE = "already_in_place"
    ALREADY_APPLIED = "already_applied"


@dataclass(frozen=True)
class RunStatus:
    run_id: str
    state: State
    approved_binding: ProposalBinding | None


class ApprovalWorkflow:
    def __init__(self, policy: PathPolicy, store: WorkflowStore) -> None:
        self._policy = policy
        self._store = store

    def start_run(self, run_id: str, actor: str) -> None:
        validate_run_id(run_id)
        with self._refusals_recorded(run_id, Action.CREATE, actor):
            if self._store.current_state(run_id) is not None:
                raise ApprovalError(f"run already exists: {run_id}")
            self._transition(run_id, Action.CREATE, actor)

    def submit(
        self,
        run_id: str,
        actor: str,
        *,
        base_sha256: str | None,
        candidate_sha256: str,
        target_path: str,
        operation_summary: dict[str, Any],
    ) -> ProposalBinding:
        with self._refusals_recorded(run_id, Action.SUBMIT, actor):
            resolved_target = self._policy.enforce(Operation.WRITE, target_path)
            proposal = ProposalBinding(
                run_id=run_id,
                proposal_id=uuid.uuid4().hex,
                base_sha256=base_sha256,
                candidate_sha256=candidate_sha256,
                target_path=str(resolved_target),
                operation_sha256=sha256_of_value(operation_summary),
            )
            self._transition(run_id, Action.SUBMIT, actor, payload=proposal.to_payload())
        return proposal

    def approve(self, run_id: str, actor: str) -> ProposalBinding:
        with self._refusals_recorded(run_id, Action.APPROVE, actor):
            next_state(self._store.current_state(run_id), Action.APPROVE)
            payload = self._store.last_payload(run_id, Action.SUBMIT)
            if payload is None:
                raise ApprovalRequiredError("nothing has been submitted for approval")
            proposal = ProposalBinding.from_payload(payload)
            self._transition(run_id, Action.APPROVE, actor, payload=proposal.to_payload())
        return proposal

    def request_revision(self, run_id: str, actor: str, reason: str) -> None:
        self._simple_transition(run_id, Action.REQUEST_REVISION, actor, {"reason": reason})

    def revise(self, run_id: str, actor: str) -> None:
        self._simple_transition(run_id, Action.REVISE, actor)

    def reject(self, run_id: str, actor: str, reason: str) -> None:
        self._simple_transition(run_id, Action.REJECT, actor, {"reason": reason})

    def edit(self, run_id: str, actor: str) -> None:
        """Editing an approved proposal invalidates its approval."""
        self._simple_transition(run_id, Action.EDIT, actor)

    def cancel(self, run_id: str, actor: str, reason: str) -> None:
        self._simple_transition(run_id, Action.CANCEL, actor, {"reason": reason})

    def apply(self, run_id: str, actor: str, candidate_path: Path) -> ApplyOutcome:
        with self._refusals_recorded(run_id, Action.APPLY, actor):
            state = self._store.current_state(run_id)
            if state is State.APPLIED:
                return ApplyOutcome.ALREADY_APPLIED
            next_state(state, Action.APPLY)
            binding = self._approved_binding(run_id)
            outcome = self._write_candidate_if_needed(binding, Path(candidate_path))
            self._transition(
                run_id,
                Action.APPLY,
                actor,
                payload={"outcome": outcome.value, "candidate_sha256": binding.candidate_sha256},
            )
        return outcome

    def record_verification(self, run_id: str, actor: str, passed: bool, details: dict[str, Any]) -> State:
        action = Action.VERIFY_PASS if passed else Action.VERIFY_FAIL
        with self._refusals_recorded(run_id, action, actor):
            self._transition(run_id, action, actor, payload=details)
        return self._store.current_state(run_id)

    def resume(self, run_id: str) -> RunStatus:
        state = self._store.current_state(run_id)
        if state is None:
            raise ApprovalError(f"unknown run: {run_id}")
        return RunStatus(run_id=run_id, state=state, approved_binding=self._active_binding(run_id, state))

    def _simple_transition(
        self,
        run_id: str,
        action: Action,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        with self._refusals_recorded(run_id, action, actor):
            self._transition(run_id, action, actor, payload=payload)

    def _transition(
        self,
        run_id: str,
        action: Action,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        current = self._store.current_state(run_id)
        target = next_state(current, action)
        self._store.append_transition(run_id, current, target, action, actor, payload or {})

    def _approved_binding(self, run_id: str) -> ProposalBinding:
        payload = self._store.last_payload(run_id, Action.APPROVE)
        if payload is None:
            raise ApprovalRequiredError("no approval exists for this run")
        return ProposalBinding.from_payload(payload)

    def _active_binding(self, run_id: str, state: State) -> ProposalBinding | None:
        if state not in APPROVAL_HOLDING_STATES:
            return None
        return self._approved_binding(run_id)

    def _write_candidate_if_needed(self, binding: ProposalBinding, candidate_path: Path) -> ApplyOutcome:
        target = self._policy.enforce(Operation.WRITE, binding.target_path)
        if str(target) != binding.target_path:
            raise StaleApprovalError("target path differs from the approved path")
        candidate_bytes = _read_candidate(candidate_path)
        if sha256_hex(candidate_bytes) != binding.candidate_sha256:
            raise StaleApprovalError("candidate file changed after approval")
        current_hash = file_sha256(target)
        if current_hash == binding.candidate_sha256:
            return ApplyOutcome.ALREADY_IN_PLACE
        if current_hash != binding.base_sha256:
            raise StaleApprovalError("target file changed after approval")
        write_bytes_atomically(target, candidate_bytes)
        return ApplyOutcome.WRITTEN

    @contextmanager
    def _refusals_recorded(self, run_id: str, action: Action, actor: str) -> Iterator[None]:
        try:
            yield
        except (ApprovalError, PolicyDeniedError) as error:
            self._store.record_attempt(run_id, action, actor, REFUSED_OUTCOME, str(error))
            raise


def _read_candidate(candidate_path: Path) -> bytes:
    try:
        return candidate_path.read_bytes()
    except OSError as error:
        raise ApprovalError(f"candidate file cannot be read: {candidate_path}") from error
