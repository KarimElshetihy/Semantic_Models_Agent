"""Staging tests: proposals are written, bound to hashes, and refused whenever the inputs are unsafe.

Each test builds its own project root in a temporary folder, with a copy of a fixture model under
tests/fixtures/ so the read policy applies exactly as it does in the real project.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssas_agent.approval import ApplyOutcome, ApprovalWorkflow, StaleApprovalError, State, WorkflowStore
from ssas_agent.audit import InvalidRunIdError
from ssas_agent.bim.document import BimDocument, sha256_hex
from ssas_agent.edit import MeasureEditError, replace_measure_expression
from ssas_agent.policy import PathPolicy, PolicyDeniedError
from ssas_agent.staging import CANDIDATE_FILE, MODEL_FILE, ChangeStager, StagingError

FIXTURE_BYTES = (Path(__file__).resolve().parents[1] / "fixtures" / "RETA_MODEL" / "Model.bim").read_bytes()
SOURCE = Path("tests/fixtures/RETA_MODEL/Model.bim")
RUN_ID = "run-staging-001"
NEW_EXPRESSION = "SUM ( 'TRX'[AMOUNT] ) + 0"
OPERATION = "replace measure expression"


def edit_amount(document):
    return replace_measure_expression(document, "TRX", "_TRX_AMOUNT", NEW_EXPRESSION)


@pytest.fixture
def project(tmp_path):
    source_file = tmp_path / SOURCE
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(FIXTURE_BYTES)
    policy = PathPolicy(project_root=tmp_path)
    store = WorkflowStore(policy, tmp_path / "artifacts" / "state" / "workflow.sqlite3")
    workflow = ApprovalWorkflow(policy, store)
    return SimpleNamespace(
        root=tmp_path,
        policy=policy,
        store=store,
        workflow=workflow,
        stager=ChangeStager(policy, workflow),
    )


def stage(project, run_id=RUN_ID, edit=edit_amount, operation=OPERATION, actor="alice"):
    return project.stager.stage(run_id, actor, SOURCE, edit, operation)


def written_paths(project):
    """Every file under the project root, as relative paths. Compared before and after a refused call."""
    return {path.relative_to(project.root).as_posix() for path in project.root.rglob("*") if path.is_file()}


def review_folder(project, run_id=RUN_ID):
    return project.root / "artifacts" / run_id


def workspace_folder(project, run_id=RUN_ID):
    return project.root / "workspaces" / run_id


def test_stage_writes_workspace_copy_candidate_and_review_files(project):
    staged = stage(project)

    expected_candidate = edit_amount(BimDocument.from_bytes(FIXTURE_BYTES)).to_bytes()
    assert staged.workspace_model.read_bytes() == FIXTURE_BYTES
    assert staged.candidate_path.read_bytes() == expected_candidate
    for name in ("diff.json", "diff.txt", "run.json", "events.jsonl"):
        assert (review_folder(project) / name).is_file(), name
    assert project.workflow.resume(RUN_ID).state is State.PROPOSED


def test_proposal_binds_base_candidate_hashes_and_the_workspace_target(project):
    staged = stage(project)

    assert staged.proposal.base_sha256 == sha256_hex(FIXTURE_BYTES)
    assert staged.proposal.candidate_sha256 == sha256_hex(staged.candidate_path.read_bytes())
    assert staged.proposal.target_path == str(staged.workspace_model.resolve())
    assert staged.workspace_model.name == MODEL_FILE
    assert staged.candidate_path.name == CANDIDATE_FILE


def test_semantic_diff_file_lists_only_the_edited_measure(project):
    stage(project)

    diff = json.loads((review_folder(project) / "diff.json").read_text(encoding="utf-8"))

    assert diff["summary"] == {"added": 0, "removed": 0, "changed": 1}
    assert [(change["identity"], change["change_kind"]) for change in diff["changes"]] == [
        ("measure:TRX/_TRX_AMOUNT", "changed"),
    ]


def test_text_diff_file_shows_the_new_expression(project):
    stage(project)

    text_diff = (review_folder(project) / "diff.txt").read_text(encoding="utf-8")

    assert any(line.startswith("+") and NEW_EXPRESSION in line for line in text_diff.splitlines())


def test_structured_review_files_never_contain_expression_text(project):
    stage(project)

    for name in ("diff.json", "run.json", "events.jsonl"):
        assert NEW_EXPRESSION not in (review_folder(project) / name).read_text(encoding="utf-8"), name


def test_run_facts_record_operation_actor_and_hashes(project):
    staged = stage(project, actor="alice")

    facts = json.loads((review_folder(project) / "run.json").read_text(encoding="utf-8"))

    assert facts["run_id"] == RUN_ID
    assert facts["operation"] == OPERATION
    assert facts["actor"] == "alice"
    assert facts["base_sha256"] == staged.proposal.base_sha256
    assert facts["candidate_sha256"] == staged.proposal.candidate_sha256


def test_raw_model_copies_are_never_written_to_artifacts(project):
    stage(project)

    names = {path.name for path in (project.root / "artifacts").rglob("*") if path.is_file()}

    assert MODEL_FILE not in names
    assert CANDIDATE_FILE not in names


def test_candidate_reads_back_to_the_edited_content(project):
    staged = stage(project)

    read_back = BimDocument.from_bytes(staged.candidate_path.read_bytes())

    assert read_back.data == edit_amount(BimDocument.from_bytes(FIXTURE_BYTES)).data


def test_refused_edit_writes_nothing_and_records_no_run(project):
    def unknown_measure(document):
        return replace_measure_expression(document, "TRX", "NO_SUCH_MEASURE", NEW_EXPRESSION)

    before = written_paths(project)

    with pytest.raises(MeasureEditError):
        stage(project, edit=unknown_measure)

    assert written_paths(project) == before
    assert project.store.current_state(RUN_ID) is None


def test_source_outside_readable_folders_is_refused(project):
    private = project.root / "private" / "Model.bim"
    private.parent.mkdir()
    private.write_bytes(FIXTURE_BYTES)

    before = written_paths(project)

    with pytest.raises(PolicyDeniedError):
        project.stager.stage(RUN_ID, "alice", Path("private/Model.bim"), edit_amount, OPERATION)

    assert written_paths(project) == before
    assert project.store.current_state(RUN_ID) is None


def test_missing_source_model_is_a_staging_error(project):
    with pytest.raises(StagingError, match="cannot be read"):
        project.stager.stage(RUN_ID, "alice", Path("tests/fixtures/NO_SUCH/Model.bim"), edit_amount, OPERATION)


def test_existing_workspace_is_refused_and_left_untouched(project):
    existing = workspace_folder(project) / MODEL_FILE
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"keep me")

    with pytest.raises(StagingError, match="workspace already exists"):
        stage(project)

    assert existing.read_bytes() == b"keep me"
    assert project.store.current_state(RUN_ID) is None


def test_second_stage_with_the_same_run_id_is_refused(project):
    stage(project)

    with pytest.raises(StagingError, match="workspace already exists"):
        stage(project)

    assert project.workflow.resume(RUN_ID).state is State.PROPOSED


@pytest.mark.parametrize("unsafe_run_id", ["../escape", "run/../../x", "", "has space"])
def test_unsafe_run_id_is_refused_before_anything_is_written(project, unsafe_run_id):
    before = written_paths(project)

    with pytest.raises(InvalidRunIdError):
        stage(project, run_id=unsafe_run_id)

    assert written_paths(project) == before


def test_blank_operation_name_is_refused(project):
    before = written_paths(project)

    with pytest.raises(StagingError, match="operation name"):
        stage(project, operation="   ")

    assert written_paths(project) == before


def test_approved_staged_change_is_applied_to_workspace_and_verified(project):
    staged = stage(project)
    project.workflow.approve(RUN_ID, "bob")

    outcome = project.workflow.apply(RUN_ID, "bob", staged.candidate_path)
    state = project.workflow.record_verification(RUN_ID, "bob", passed=True, details={"check": "round-trip"})

    assert outcome is ApplyOutcome.WRITTEN
    assert staged.workspace_model.read_bytes() == staged.candidate_path.read_bytes()
    assert state is State.VERIFIED


def test_candidate_changed_after_staging_is_refused_at_apply(project):
    staged = stage(project)
    project.workflow.approve(RUN_ID, "bob")
    staged.candidate_path.write_bytes(b'{"model": {"tampered": true}}')

    with pytest.raises(StaleApprovalError, match="candidate file changed"):
        project.workflow.apply(RUN_ID, "bob", staged.candidate_path)

    assert staged.workspace_model.read_bytes() == FIXTURE_BYTES
    assert project.workflow.resume(RUN_ID).state is State.APPROVED


def test_same_change_gives_the_same_operation_hash_in_different_runs(project):
    first = stage(project, run_id="run-staging-a")
    second = stage(project, run_id="run-staging-b")

    assert first.proposal.operation_sha256 == second.proposal.operation_sha256
    assert first.proposal.proposal_id != second.proposal.proposal_id


def test_change_summary_is_returned_for_the_caller(project):
    staged = stage(project)

    assert staged.change_summary == {"added": 0, "removed": 0, "changed": 1}


def test_expression_edit_is_categorised_for_review_not_breaking(project):
    staged = stage(project)

    assert staged.category_summary == {"breaking": 0, "review": 1, "additive": 0, "cosmetic": 0}
    diff = json.loads((review_folder(project) / "diff.json").read_text(encoding="utf-8"))
    assert diff["changes"][0]["category"] == "review"
    assert diff["categories"]["review"] == 1


def test_run_facts_include_category_summary(project):
    stage(project)

    facts = json.loads((review_folder(project) / "run.json").read_text(encoding="utf-8"))

    assert facts["category_summary"] == {"breaking": 0, "review": 1, "additive": 0, "cosmetic": 0}
