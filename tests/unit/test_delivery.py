"""Step 9: approved changes are written to one named destination, only after a separate human approval.

Each test builds its own project root in a temporary folder. The destination folder is `output/`, the project
default. The command line is tested by calling `main` with scripted input, so no terminal is needed."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssas_agent.approval import (
    ApplyOutcome,
    ApprovalWorkflow,
    InvalidTransitionError,
    StaleApprovalError,
    State,
    WorkflowStore,
)
from ssas_agent.bim.document import sha256_hex
from ssas_agent.cli import main
from ssas_agent.delivery import DeliveryEvent, apply_and_verify, approve_change, verify_target
from ssas_agent.delivery.prompts import describe_proposal
from ssas_agent.edit import replace_measure_expression
from ssas_agent.policy import (
    DEFAULT_APPLY_FOLDER,
    Operation,
    PathPolicy,
    PolicyConfigurationError,
    PolicyDeniedError,
)
from ssas_agent.staging import ChangeStager, StagingError

FIXTURE_BYTES = (Path(__file__).resolve().parents[1] / "fixtures" / "RETA_MODEL" / "Model.bim").read_bytes()
SOURCE = Path("tests/fixtures/RETA_MODEL/Model.bim")
DESTINATION = Path(DEFAULT_APPLY_FOLDER) / "Model.bim"
RUN_ID = "run-delivery-001"
NEW_EXPRESSION = "SUM ( 'TRX'[AMOUNT] ) + 0"
OPERATION = "replace measure expression"
APPROVER = "bob"


def edit_amount(document):
    return replace_measure_expression(document, "TRX", "_TRX_AMOUNT", NEW_EXPRESSION)


@pytest.fixture
def project(tmp_path):
    source_file = tmp_path / SOURCE
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(FIXTURE_BYTES)
    policy = PathPolicy(project_root=tmp_path, apply_folder=Path(DEFAULT_APPLY_FOLDER))
    store = WorkflowStore(policy, tmp_path / "artifacts" / "state" / "workflow.sqlite3")
    workflow = ApprovalWorkflow(policy, store)
    return SimpleNamespace(
        root=tmp_path,
        policy=policy,
        workflow=workflow,
        stager=ChangeStager(policy, workflow),
        destination=tmp_path / DESTINATION,
    )


def place_destination_model(project, data=FIXTURE_BYTES):
    project.destination.parent.mkdir(parents=True, exist_ok=True)
    project.destination.write_bytes(data)


def stage_to_destination(project, source=SOURCE, run_id=RUN_ID):
    return project.stager.stage(run_id, "alice", source, edit_amount, OPERATION, target_model=DESTINATION)


def written_paths(project):
    return {path.relative_to(project.root).as_posix() for path in project.root.rglob("*") if path.is_file()}


def event_names(project, run_id=RUN_ID):
    lines = (project.root / "artifacts" / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["event"] for line in lines]


def run_cli(project, *arguments, answer="approve"):
    """Run the command line against the project; returns (exit code, printed lines)."""
    printed = []
    exit_code = main(
        ["--project-root", str(project.root), *arguments],
        read_line=lambda prompt: answer,
        write_line=printed.append,
    )
    return exit_code, printed


def never_asked(prompt):
    raise AssertionError(f"the approver must not be asked anything here: {prompt}")


# ---- Policy ---------------------------------------------------------------------------------------


def test_only_the_destination_model_file_is_opened_up(project):
    allowed_read = project.policy.decide(Operation.READ, DESTINATION)
    allowed_write = project.policy.decide(Operation.WRITE, DESTINATION)

    assert allowed_read.allowed and allowed_write.allowed
    for other in ("output/Other.bim", "output/sub/Model.bim", "output/Model.bim.bak", "Model.bim"):
        assert not project.policy.decide(Operation.WRITE, other).allowed, other
        assert not project.policy.decide(Operation.READ, other).allowed, other


def test_without_a_named_destination_nothing_in_output_is_allowed(tmp_path):
    policy = PathPolicy(project_root=tmp_path)

    assert policy.apply_target is None
    assert not policy.decide(Operation.WRITE, DESTINATION).allowed
    assert not policy.decide(Operation.READ, DESTINATION).allowed


def test_destination_outside_the_project_root_is_allowed_for_model_bim_only(tmp_path):
    vs_project = tmp_path / "vs_project"
    policy = PathPolicy(project_root=tmp_path / "repo", apply_folder=vs_project)

    assert policy.decide(Operation.WRITE, vs_project / "Model.bim").allowed
    assert not policy.decide(Operation.WRITE, vs_project / "Model.smproj").allowed
    assert not policy.decide(Operation.WRITE, vs_project / "sub" / "Model.bim").allowed


@pytest.mark.parametrize(
    "unsafe_folder",
    [".", "..", "tests", "tests/fixtures", "tests/fixtures/RETA_MODEL", "example_models", "workspaces", "artifacts/state", "knowledge", "specs"],
)
def test_destination_that_overlaps_the_project_or_its_policy_folders_is_refused(tmp_path, unsafe_folder):
    with pytest.raises(PolicyConfigurationError):
        PathPolicy(project_root=tmp_path, apply_folder=Path(unsafe_folder))


def test_destination_that_is_a_file_is_refused(tmp_path):
    (tmp_path / "plain_file").write_text("x", encoding="utf-8")

    with pytest.raises(PolicyConfigurationError, match="is a file"):
        PathPolicy(project_root=tmp_path, apply_folder=Path("plain_file"))


def test_fixtures_stay_protected_when_a_destination_is_named(project):
    assert not project.policy.decide(Operation.WRITE, SOURCE).allowed


# ---- Staging to the destination -------------------------------------------------------------------


def test_staging_to_a_new_destination_binds_a_new_file_and_writes_nothing_there(project):
    staged = stage_to_destination(project)

    assert staged.proposal.target_path == str(project.destination)
    assert staged.proposal.base_sha256 is None
    assert not project.destination.exists()
    assert staged.workspace_model.read_bytes() == FIXTURE_BYTES
    assert project.workflow.resume(RUN_ID).state is State.PROPOSED


def test_staging_from_the_destination_itself_binds_its_hash_and_keeps_the_original_as_backup(project):
    place_destination_model(project)

    staged = stage_to_destination(project, source=DESTINATION)

    assert staged.proposal.base_sha256 == sha256_hex(FIXTURE_BYTES)
    assert staged.workspace_model.read_bytes() == FIXTURE_BYTES
    assert project.destination.read_bytes() == FIXTURE_BYTES


def test_staging_from_another_model_over_an_existing_destination_is_refused_and_writes_nothing(project):
    place_destination_model(project, b'{"name": "someone else\'s model"}')
    before = written_paths(project)

    with pytest.raises(StagingError, match="already holds a model"):
        stage_to_destination(project, source=SOURCE)

    assert written_paths(project) == before
    assert project.destination.read_bytes() == b'{"name": "someone else\'s model"}'


def test_a_target_outside_the_destination_is_refused_by_the_policy(project):
    with pytest.raises(PolicyDeniedError):
        project.stager.stage(RUN_ID, "alice", SOURCE, edit_amount, OPERATION, target_model=SOURCE)


# ---- Approve, apply, verify -----------------------------------------------------------------------


def test_full_cycle_creates_the_destination_model_and_verifies_it(project):
    staged = stage_to_destination(project)

    approve_change(project.workflow, project.policy, RUN_ID, APPROVER)
    result = apply_and_verify(project.workflow, project.policy, RUN_ID, APPROVER)

    assert result.verified and result.state is State.VERIFIED
    assert result.outcome is ApplyOutcome.WRITTEN
    assert project.destination.read_bytes() == staged.candidate_path.read_bytes()
    assert event_names(project) == ["staged", "submitted", "approved", "applied", "verified"]


def test_full_cycle_replaces_an_existing_destination_and_leaves_the_original_in_the_workspace(project):
    place_destination_model(project)
    staged = stage_to_destination(project, source=DESTINATION)

    approve_change(project.workflow, project.policy, RUN_ID, APPROVER)
    result = apply_and_verify(project.workflow, project.policy, RUN_ID, APPROVER)

    assert result.verified
    assert project.destination.read_bytes() == staged.candidate_path.read_bytes()
    assert project.destination.read_bytes() != FIXTURE_BYTES
    assert staged.workspace_model.read_bytes() == FIXTURE_BYTES


def test_apply_without_approval_is_refused_and_writes_nothing(project):
    stage_to_destination(project)

    with pytest.raises(InvalidTransitionError):
        apply_and_verify(project.workflow, project.policy, RUN_ID, APPROVER)

    assert not project.destination.exists()
    assert project.workflow.resume(RUN_ID).state is State.PROPOSED


def test_destination_changed_after_approval_is_never_overwritten(project):
    place_destination_model(project)
    stage_to_destination(project, source=DESTINATION)
    approve_change(project.workflow, project.policy, RUN_ID, APPROVER)
    project.destination.write_bytes(FIXTURE_BYTES + b"\r\n")

    with pytest.raises(StaleApprovalError, match="target file changed"):
        apply_and_verify(project.workflow, project.policy, RUN_ID, APPROVER)

    assert project.destination.read_bytes() == FIXTURE_BYTES + b"\r\n"
    assert project.workflow.resume(RUN_ID).state is State.APPROVED


def test_destination_created_after_staging_is_never_overwritten(project):
    stage_to_destination(project)
    approve_change(project.workflow, project.policy, RUN_ID, APPROVER)
    place_destination_model(project, b"made by someone while the change waited")

    with pytest.raises(StaleApprovalError, match="target file changed"):
        apply_and_verify(project.workflow, project.policy, RUN_ID, APPROVER)

    assert project.destination.read_bytes() == b"made by someone while the change waited"


def test_applying_twice_is_refused(project):
    stage_to_destination(project)
    approve_change(project.workflow, project.policy, RUN_ID, APPROVER)
    apply_and_verify(project.workflow, project.policy, RUN_ID, APPROVER)

    with pytest.raises(InvalidTransitionError):
        apply_and_verify(project.workflow, project.policy, RUN_ID, APPROVER)


def test_failed_verification_is_recorded_as_failed(project, monkeypatch):
    stage_to_destination(project)
    approve_change(project.workflow, project.policy, RUN_ID, APPROVER)
    monkeypatch.setattr("ssas_agent.delivery.apply._reads_back_identically", lambda target: False)

    result = apply_and_verify(project.workflow, project.policy, RUN_ID, APPROVER)

    assert not result.verified and result.state is State.FAILED
    assert result.verification["hash_matches"] is True
    assert result.verification["reads_back_identically"] is False
    assert event_names(project)[-1] == DeliveryEvent.VERIFICATION_FAILED


def test_verify_target_fails_when_the_file_differs_from_the_approved_candidate(project):
    staged = stage_to_destination(project)
    project.destination.parent.mkdir(parents=True, exist_ok=True)
    project.destination.write_bytes(b"not the candidate")

    passed, details = verify_target(staged.proposal)

    assert passed is False
    assert details["hash_matches"] is False


# ---- Command line ---------------------------------------------------------------------------------


def test_describe_proposal_says_when_a_new_file_will_be_created(project):
    staged = stage_to_destination(project)

    lines = describe_proposal(staged.proposal)

    assert any("creates a new file" in line for line in lines)
    assert any(str(project.destination) in line for line in lines)


def test_approve_command_records_the_approval_only_after_the_word_is_typed(project):
    stage_to_destination(project)

    exit_code, printed = run_cli(project, "approve", "--run-id", RUN_ID, "--actor", APPROVER)

    assert exit_code == 0
    assert project.workflow.resume(RUN_ID).state is State.APPROVED
    assert any("Approved by bob" in line for line in printed)
    assert not project.destination.exists()


def test_approve_command_with_another_answer_changes_nothing(project):
    stage_to_destination(project)

    exit_code, printed = run_cli(project, "approve", "--run-id", RUN_ID, "--actor", APPROVER, answer="yes")

    assert exit_code == 1
    assert project.workflow.resume(RUN_ID).state is State.PROPOSED
    assert "Not approved. Nothing was changed." in printed


def test_approve_command_refuses_a_run_that_is_not_waiting_without_asking(project):
    stage_to_destination(project)
    approve_change(project.workflow, project.policy, RUN_ID, APPROVER)

    printed = []
    exit_code = main(
        ["--project-root", str(project.root), "approve", "--run-id", RUN_ID, "--actor", APPROVER],
        read_line=never_asked,
        write_line=printed.append,
    )

    assert exit_code == 1
    assert printed[-1].startswith("Refused:") and "not waiting for approval" in printed[-1]


def test_apply_command_writes_and_verifies_after_approval(project):
    staged = stage_to_destination(project)
    run_cli(project, "approve", "--run-id", RUN_ID, "--actor", APPROVER)

    exit_code, printed = run_cli(project, "apply", "--run-id", RUN_ID, "--actor", APPROVER)

    assert exit_code == 0
    assert project.destination.read_bytes() == staged.candidate_path.read_bytes()
    assert any("State:      VERIFIED" in line for line in printed)


def test_apply_command_before_approval_is_refused(project):
    stage_to_destination(project)

    exit_code, printed = run_cli(project, "apply", "--run-id", RUN_ID, "--actor", APPROVER)

    assert exit_code == 1
    assert printed[-1].startswith("Refused:")
    assert not project.destination.exists()


def test_command_for_an_unknown_run_is_refused(project):
    exit_code, printed = run_cli(project, "approve", "--run-id", "run-does-not-exist", "--actor", APPROVER)

    assert exit_code == 1
    assert printed[-1].startswith("Refused:")


def test_command_with_an_invalid_run_id_is_refused(project):
    exit_code, printed = run_cli(project, "apply", "--run-id", "../escape", "--actor", APPROVER)

    assert exit_code == 1
    assert printed[-1].startswith("Refused:")


def test_command_with_a_blank_actor_is_a_usage_error(project):
    with pytest.raises(SystemExit) as raised:
        run_cli(project, "approve", "--run-id", RUN_ID, "--actor", "   ")

    assert raised.value.code == 2


def test_command_with_an_unsafe_destination_folder_is_refused(project):
    exit_code, printed = run_cli(project, "--apply-folder", ".", "approve", "--run-id", RUN_ID, "--actor", APPROVER)

    assert exit_code == 1
    assert "project root" in printed[-1]
