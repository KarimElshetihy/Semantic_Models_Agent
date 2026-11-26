"""Approval workflow tests: enforced apply, stale approvals, idempotent resume, persistence and tamper detection."""

import sqlite3
from types import SimpleNamespace

import pytest

from ssas_agent.approval import (
    Action,
    ApplyOutcome,
    ApprovalError,
    ApprovalWorkflow,
    InvalidTransitionError,
    StaleApprovalError,
    State,
    WorkflowStore,
)
from ssas_agent.audit import InvalidRunIdError
from ssas_agent.bim.document import sha256_hex
from ssas_agent.policy import PathPolicy, PolicyDeniedError

RUN_ID = "run-approval-001"
BASE_BYTES = b'{"model": {"culture": "en-US"}}'
CANDIDATE_BYTES = b'{"model": {"culture": "ar-EG"}}'
OPERATION_SUMMARY = {"change": "culture"}


@pytest.fixture
def project(tmp_path):
    policy = PathPolicy(project_root=tmp_path)
    store = WorkflowStore(policy, tmp_path / "artifacts" / "state" / "workflow.sqlite3")
    return SimpleNamespace(root=tmp_path, policy=policy, store=store, workflow=ApprovalWorkflow(policy, store))


@pytest.fixture
def files(project):
    run_folder = project.root / "workspaces" / RUN_ID
    run_folder.mkdir(parents=True)
    target = run_folder / "Model.bim"
    target.write_bytes(BASE_BYTES)
    candidate = run_folder / "candidate.bim"
    candidate.write_bytes(CANDIDATE_BYTES)
    return SimpleNamespace(target=target, candidate=candidate)


def propose(project, files, base_bytes=BASE_BYTES):
    base_hash = None if base_bytes is None else sha256_hex(base_bytes)
    return project.workflow.submit(
        RUN_ID,
        "alice",
        base_sha256=base_hash,
        candidate_sha256=sha256_hex(CANDIDATE_BYTES),
        target_path=str(files.target),
        operation_summary=OPERATION_SUMMARY,
    )


def start_and_propose(project, files):
    project.workflow.start_run(RUN_ID, "alice")
    return propose(project, files)


def state_of(project):
    return project.workflow.resume(RUN_ID).state


def test_approved_candidate_is_applied_and_verified(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")

    outcome = project.workflow.apply(RUN_ID, "bob", files.candidate)
    state = project.workflow.record_verification(RUN_ID, "bob", passed=True, details={"check": "round-trip"})

    assert outcome is ApplyOutcome.WRITTEN
    assert files.target.read_bytes() == CANDIDATE_BYTES
    assert state is State.VERIFIED
    assert [row["to_state"] for row in project.store.transitions(RUN_ID)] == [
        "DRAFT", "PROPOSED", "APPROVED", "APPLIED", "VERIFIED",
    ]


def test_apply_is_refused_before_approval_and_leaves_target_unchanged(project, files):
    start_and_propose(project, files)

    with pytest.raises(InvalidTransitionError):
        project.workflow.apply(RUN_ID, "bob", files.candidate)

    assert files.target.read_bytes() == BASE_BYTES
    assert project.store.attempts(RUN_ID)[-1]["action"] == "apply"
    assert project.store.attempts(RUN_ID)[-1]["outcome"] == "refused"


def test_apply_refused_when_candidate_changed_after_approval(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")
    files.candidate.write_bytes(b'{"model": {"culture": "tampered"}}')

    with pytest.raises(StaleApprovalError, match="candidate file changed"):
        project.workflow.apply(RUN_ID, "bob", files.candidate)

    assert files.target.read_bytes() == BASE_BYTES
    assert state_of(project) is State.APPROVED


def test_apply_refused_when_target_changed_after_approval(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")
    files.target.write_bytes(b'{"model": {"culture": "someone-else"}}')

    with pytest.raises(StaleApprovalError, match="target file changed"):
        project.workflow.apply(RUN_ID, "bob", files.candidate)

    assert files.target.read_bytes() == b'{"model": {"culture": "someone-else"}}'
    assert state_of(project) is State.APPROVED


def test_edit_after_approval_invalidates_it(project, files):
    first = start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")
    project.workflow.edit(RUN_ID, "alice")

    assert state_of(project) is State.DRAFT
    assert project.workflow.resume(RUN_ID).approved_binding is None
    with pytest.raises(InvalidTransitionError):
        project.workflow.apply(RUN_ID, "bob", files.candidate)

    second = propose(project, files)
    project.workflow.approve(RUN_ID, "bob")

    assert second.proposal_id != first.proposal_id
    assert project.workflow.resume(RUN_ID).approved_binding.proposal_id == second.proposal_id


def test_rejected_proposal_cannot_be_approved(project, files):
    start_and_propose(project, files)
    project.workflow.reject(RUN_ID, "bob", reason="not needed")

    assert state_of(project) is State.REJECTED
    with pytest.raises(InvalidTransitionError):
        project.workflow.approve(RUN_ID, "bob")


def test_revision_cycle_returns_to_draft(project, files):
    start_and_propose(project, files)
    project.workflow.request_revision(RUN_ID, "bob", reason="explain the change")
    assert state_of(project) is State.REVISION_REQUESTED

    project.workflow.revise(RUN_ID, "alice")

    assert state_of(project) is State.DRAFT


def test_cancel_is_refused_after_apply(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")
    project.workflow.apply(RUN_ID, "bob", files.candidate)

    with pytest.raises(InvalidTransitionError):
        project.workflow.cancel(RUN_ID, "bob", reason="too late")
    assert state_of(project) is State.APPLIED


def test_resume_after_crash_between_write_and_record_does_not_rewrite(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")
    files.target.write_bytes(CANDIDATE_BYTES)

    outcome = project.workflow.apply(RUN_ID, "bob", files.candidate)

    assert outcome is ApplyOutcome.ALREADY_IN_PLACE
    assert state_of(project) is State.APPLIED
    assert [row["action"] for row in project.store.transitions(RUN_ID)].count("apply") == 1


def test_second_apply_is_idempotent(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")
    project.workflow.apply(RUN_ID, "bob", files.candidate)

    outcome = project.workflow.apply(RUN_ID, "bob", files.candidate)

    assert outcome is ApplyOutcome.ALREADY_APPLIED
    assert [row["action"] for row in project.store.transitions(RUN_ID)].count("apply") == 1


def test_new_file_target_is_created_on_apply(project, files):
    files.target.unlink()
    project.workflow.start_run(RUN_ID, "alice")
    propose(project, files, base_bytes=None)
    project.workflow.approve(RUN_ID, "bob")

    outcome = project.workflow.apply(RUN_ID, "bob", files.candidate)

    assert outcome is ApplyOutcome.WRITTEN
    assert files.target.read_bytes() == CANDIDATE_BYTES


def test_target_outside_workspaces_is_refused_at_submit(project, files):
    project.workflow.start_run(RUN_ID, "alice")
    protected = project.root / "example_models" / "EOPM_MODEL" / "Model.bim"

    with pytest.raises(PolicyDeniedError, match="protected"):
        project.workflow.submit(
            RUN_ID,
            "alice",
            base_sha256=None,
            candidate_sha256=sha256_hex(CANDIDATE_BYTES),
            target_path=str(protected),
            operation_summary=OPERATION_SUMMARY,
        )

    assert state_of(project) is State.DRAFT
    assert project.store.attempts(RUN_ID)[-1]["action"] == "submit"


def test_approve_without_submit_is_refused(project, files):
    project.workflow.start_run(RUN_ID, "alice")

    with pytest.raises(InvalidTransitionError):
        project.workflow.approve(RUN_ID, "bob")


def test_apply_without_any_approval_record_is_refused(project, files):
    start_and_propose(project, files)

    with pytest.raises(InvalidTransitionError):
        project.workflow.apply(RUN_ID, "bob", files.candidate)
    assert not any(row["action"] == "approve" for row in project.store.transitions(RUN_ID))


def test_run_cannot_be_started_twice(project):
    project.workflow.start_run(RUN_ID, "alice")

    with pytest.raises(ApprovalError, match="already exists"):
        project.workflow.start_run(RUN_ID, "alice")


def test_unsafe_run_id_is_rejected(project):
    with pytest.raises(InvalidRunIdError):
        project.workflow.start_run("../escape", "alice")


def test_resume_of_unknown_run_is_refused(project):
    with pytest.raises(ApprovalError, match="unknown run"):
        project.workflow.resume("never-started")


def test_state_survives_a_new_store_and_workflow(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")

    reopened_store = WorkflowStore(project.policy, project.store.db_path)
    reopened = ApprovalWorkflow(project.policy, reopened_store)

    status = reopened.resume(RUN_ID)
    assert status.state is State.APPROVED
    assert status.approved_binding.candidate_sha256 == sha256_hex(CANDIDATE_BYTES)


def test_stored_payloads_pass_integrity_check(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")

    assert project.store.verify_integrity(RUN_ID)


def test_tampered_payload_fails_integrity_check(project, files):
    start_and_propose(project, files)
    project.workflow.approve(RUN_ID, "bob")
    with sqlite3.connect(project.store.db_path) as connection:
        connection.execute(
            "UPDATE transitions SET payload_json = '{}' WHERE run_id = ? AND action = 'approve'",
            (RUN_ID,),
        )

    assert not project.store.verify_integrity(RUN_ID)


def test_approval_binding_records_hashes_and_resolved_target(project, files):
    proposal = start_and_propose(project, files)

    assert proposal.base_sha256 == sha256_hex(BASE_BYTES)
    assert proposal.candidate_sha256 == sha256_hex(CANDIDATE_BYTES)
    assert proposal.target_path == str(files.target.resolve())
    assert proposal.run_id == RUN_ID


def test_new_file_base_hash_is_none(project, files):
    files.target.unlink()
    project.workflow.start_run(RUN_ID, "alice")

    proposal = propose(project, files, base_bytes=None)

    assert proposal.base_sha256 is None
