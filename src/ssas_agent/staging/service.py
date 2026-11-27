"""Stage a proposed model change for review.

Order of work matters:
1. Read the source model and build the candidate in memory. A refused edit writes nothing.
2. Check the run ID, the policy and that the workspace is free. Nothing is written yet.
3. Start the run in the workflow store, write the workspace copies and the review files, then submit.

Staging stops at PROPOSED. Approval and apply are separate calls on the workflow.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ssas_agent.approval import ApprovalWorkflow
from ssas_agent.audit import RunRecorder, validate_run_id
from ssas_agent.bim.document import BimDocument, sha256_hex
from ssas_agent.bim.storage import write_bytes_atomically
from ssas_agent.diff import VersionComparison, compare_documents
from ssas_agent.policy import Operation, PathPolicy
from ssas_agent.staging.records import StagedChange, StagingError
from ssas_agent.staging.review_files import write_review_files

WORKSPACES_FOLDER = "workspaces"
ARTIFACTS_FOLDER = "artifacts"
MODEL_FILE = "Model.bim"
CANDIDATE_FILE = "candidate.bim"

Edit = Callable[[BimDocument], BimDocument]


@dataclass(frozen=True)
class PreparedChange:
    """Everything a change needs, computed in memory before any write."""

    source_path: Path
    source_bytes: bytes
    candidate_bytes: bytes
    base_sha256: str
    candidate_sha256: str
    comparison: VersionComparison


class ChangeStager:
    def __init__(self, policy: PathPolicy, workflow: ApprovalWorkflow) -> None:
        self._policy = policy
        self._workflow = workflow

    def stage(
        self,
        run_id: str,
        actor: str,
        source_model: Path,
        edit: Edit,
        operation_name: str,
    ) -> StagedChange:
        validate_run_id(run_id)
        _require_text(operation_name, "operation name")
        prepared = self._prepare(source_model, edit)
        workspace_model = self._workspace_path(run_id, MODEL_FILE)
        candidate_path = self._workspace_path(run_id, CANDIDATE_FILE)
        _refuse_if_workspace_exists(workspace_model)

        operation_summary = {"operation": operation_name, "comparison": prepared.comparison.to_payload()}
        self._workflow.start_run(run_id, actor)
        recorder = RunRecorder(self._policy, Path(ARTIFACTS_FOLDER), run_id)
        write_bytes_atomically(workspace_model, prepared.source_bytes)
        write_bytes_atomically(candidate_path, prepared.candidate_bytes)
        run_facts = _run_facts(run_id, operation_name, actor, prepared, workspace_model, candidate_path)
        write_review_files(recorder, prepared.comparison, run_facts)
        recorder.append_event("staged", {"actor": actor, "operation": operation_name})
        proposal = self._workflow.submit(
            run_id,
            actor,
            base_sha256=prepared.base_sha256,
            candidate_sha256=prepared.candidate_sha256,
            target_path=str(workspace_model),
            operation_summary=operation_summary,
        )
        recorder.append_event("submitted", {"actor": actor, "proposal_id": proposal.proposal_id})
        return StagedChange(
            run_id=run_id,
            proposal=proposal,
            workspace_model=workspace_model,
            candidate_path=candidate_path,
            review_folder=recorder.run_dir,
            change_summary=prepared.comparison.semantic.summary(),
            category_summary=prepared.comparison.category_summary(),
        )

    def _prepare(self, source_model: Path, edit: Edit) -> PreparedChange:
        source_path = self._policy.enforce(Operation.READ, source_model)
        source_bytes = _read_source(source_path)
        source_document = BimDocument.from_bytes(source_bytes)
        edited = edit(source_document)
        candidate_bytes = edited.to_bytes()
        _verify_candidate(candidate_bytes, edited)
        return PreparedChange(
            source_path=source_path,
            source_bytes=source_bytes,
            candidate_bytes=candidate_bytes,
            base_sha256=sha256_hex(source_bytes),
            candidate_sha256=sha256_hex(candidate_bytes),
            comparison=compare_documents(source_document, edited, MODEL_FILE),
        )

    def _workspace_path(self, run_id: str, file_name: str) -> Path:
        return self._policy.enforce(Operation.WRITE, Path(WORKSPACES_FOLDER) / run_id / file_name)


def _read_source(source_path: Path) -> bytes:
    try:
        return source_path.read_bytes()
    except OSError as error:
        raise StagingError(f"source model cannot be read: {source_path}") from error


def _verify_candidate(candidate_bytes: bytes, edited: BimDocument) -> None:
    """The candidate file must read back to exactly the edited content."""
    if BimDocument.from_bytes(candidate_bytes).data != edited.data:
        raise StagingError("candidate does not read back to the edited content")


def _refuse_if_workspace_exists(workspace_model: Path) -> None:
    if workspace_model.parent.exists():
        raise StagingError(f"workspace already exists for this run: {workspace_model.parent}")


def _require_text(value: str, label: str) -> None:
    if not value.strip():
        raise StagingError(f"{label} must not be blank")


def _run_facts(
    run_id: str,
    operation_name: str,
    actor: str,
    prepared: PreparedChange,
    workspace_model: Path,
    candidate_path: Path,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "operation": operation_name,
        "actor": actor,
        "source_model": str(prepared.source_path),
        "workspace_model": str(workspace_model),
        "candidate": str(candidate_path),
        "base_sha256": prepared.base_sha256,
        "candidate_sha256": prepared.candidate_sha256,
        "change_summary": prepared.comparison.semantic.summary(),
        "category_summary": prepared.comparison.category_summary(),
    }
