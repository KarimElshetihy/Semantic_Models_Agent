"""Measure edit tests: exact, typed changes that keep unrelated metadata, plus one end-to-end approved application."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssas_agent.approval import ApplyOutcome, ApprovalWorkflow, State, WorkflowStore
from ssas_agent.bim import NonReproducibleBimError
from ssas_agent.bim.document import BimDocument, sha256_hex
from ssas_agent.bim.storage import write_bytes_atomically
from ssas_agent.diff import diff_inventories, unified_text_diff
from ssas_agent.edit import MeasureEditError, add_measure, replace_measure_expression
from ssas_agent.inventory import build_inventory
from ssas_agent.policy import PathPolicy

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RETA_BYTES = (FIXTURES / "RETA_MODEL" / "Model.bim").read_bytes()
STRING_MEASURE = ("TRX", "_TRX_AMOUNT")
LIST_MEASURE = ("TRX_COUNT", "_TRX_COUNT")
NEW_EXPRESSION = "SUM ( 'TRX'[AMOUNT] ) + 0"
RUN_ID = "run-measure-001"


def load_reta() -> BimDocument:
    return BimDocument.from_bytes(RETA_BYTES)


def find_measure(data: dict, table_name: str, measure_name: str) -> dict:
    table = next(table for table in data["model"]["tables"] if table["name"] == table_name)
    return next(measure for measure in table["measures"] if measure["name"] == measure_name)


def without_expression(data: dict, table_name: str, measure_name: str) -> dict:
    """A copy of the document with one measure's expression removed, for comparing everything else."""
    stripped = copy.deepcopy(data)
    del find_measure(stripped, table_name, measure_name)["expression"]
    return stripped


def test_replacing_string_expression_changes_only_that_expression():
    original = load_reta()

    edited = replace_measure_expression(original, *STRING_MEASURE, NEW_EXPRESSION)

    assert find_measure(edited.data, *STRING_MEASURE)["expression"] == NEW_EXPRESSION
    assert without_expression(edited.data, *STRING_MEASURE) == without_expression(original.data, *STRING_MEASURE)


def test_replacing_list_expression_keeps_list_form():
    original = load_reta()

    edited = replace_measure_expression(original, *LIST_MEASURE, NEW_EXPRESSION)

    stored = find_measure(edited.data, *LIST_MEASURE)["expression"]
    assert stored == [NEW_EXPRESSION]


def test_multiline_expression_is_split_only_when_original_was_a_list():
    multiline = "VAR x = 1\nRETURN x"

    as_list = replace_measure_expression(load_reta(), *LIST_MEASURE, multiline)
    as_string = replace_measure_expression(load_reta(), *STRING_MEASURE, multiline)

    assert find_measure(as_list.data, *LIST_MEASURE)["expression"] == ["VAR x = 1", "RETURN x"]
    assert find_measure(as_string.data, *STRING_MEASURE)["expression"] == multiline


def test_windows_line_endings_in_new_expression_are_normalized():
    edited = replace_measure_expression(load_reta(), *LIST_MEASURE, "VAR x = 1\r\nRETURN x")

    assert find_measure(edited.data, *LIST_MEASURE)["expression"] == ["VAR x = 1", "RETURN x"]


def test_semantic_diff_reports_only_the_edited_measure():
    original = load_reta()
    edited = replace_measure_expression(original, *STRING_MEASURE, NEW_EXPRESSION)

    diff = diff_inventories(build_inventory(original.data), build_inventory(edited.data))

    assert [(change.identity, change.change_kind) for change in diff.changes] == [
        ("measure:TRX/_TRX_AMOUNT", "changed"),
    ]
    assert diff.changes[0].changed_properties == ("expression",)


def test_text_diff_shows_the_new_expression_line():
    original = load_reta()
    edited = replace_measure_expression(original, *STRING_MEASURE, NEW_EXPRESSION)

    text_diff = unified_text_diff(original.source_bytes, edited.to_bytes(), "Model.bim")

    added_lines = [line for line in text_diff.splitlines() if line.startswith("+") and not line.startswith("+++")]
    assert len(added_lines) == 1
    assert NEW_EXPRESSION in added_lines[0]


def test_unchanged_expression_is_refused():
    original = load_reta()
    current = expression_of(original, *STRING_MEASURE)

    with pytest.raises(MeasureEditError, match="unchanged"):
        replace_measure_expression(original, *STRING_MEASURE, current)


def expression_of(document: BimDocument, table_name: str, measure_name: str) -> str:
    stored = find_measure(document.data, table_name, measure_name)["expression"]
    return "\n".join(stored) if isinstance(stored, list) else stored


@pytest.mark.parametrize(
    "table_name, measure_name",
    [("NO_SUCH_TABLE", "_TRX_AMOUNT"), ("TRX", "NO_SUCH_MEASURE")],
)
def test_unknown_table_or_measure_is_refused(table_name, measure_name):
    with pytest.raises(MeasureEditError, match="exist exactly once"):
        replace_measure_expression(load_reta(), table_name, measure_name, NEW_EXPRESSION)


@pytest.mark.parametrize("blank", ["", "   ", "\n"])
def test_blank_expression_is_refused(blank):
    with pytest.raises(MeasureEditError, match="blank"):
        replace_measure_expression(load_reta(), *STRING_MEASURE, blank)


def test_edit_does_not_change_the_input_document():
    original = load_reta()
    data_before = copy.deepcopy(original.data)

    replace_measure_expression(original, *STRING_MEASURE, NEW_EXPRESSION)

    assert original.data == data_before
    assert original.to_bytes() == RETA_BYTES


def test_edit_is_refused_for_a_file_that_cannot_be_reproduced():
    lf_only_bytes = RETA_BYTES.replace(b"\r\n", b"\n")
    document = BimDocument.from_bytes(lf_only_bytes)

    with pytest.raises(NonReproducibleBimError):
        replace_measure_expression(document, *STRING_MEASURE, NEW_EXPRESSION)


def test_add_measure_appends_one_measure_and_nothing_else():
    original = load_reta()

    edited = add_measure(original, "TRX", "_TRX_NEW", NEW_EXPRESSION)

    diff = diff_inventories(build_inventory(original.data), build_inventory(edited.data))
    assert [(change.identity, change.change_kind) for change in diff.changes] == [
        ("measure:TRX/_TRX_NEW", "added"),
    ]
    assert find_measure(edited.data, "TRX", "_TRX_NEW")["expression"] == NEW_EXPRESSION


def test_add_measure_uses_list_form_only_for_multiline_expressions():
    edited = add_measure(load_reta(), "TRX", "_TRX_NEW", "VAR x = 1\nRETURN x")

    assert find_measure(edited.data, "TRX", "_TRX_NEW")["expression"] == ["VAR x = 1", "RETURN x"]


def test_add_measure_with_existing_name_is_refused():
    with pytest.raises(MeasureEditError, match="already exists"):
        add_measure(load_reta(), "TRX", "_TRX_AMOUNT", NEW_EXPRESSION)


@pytest.fixture
def workspace(tmp_path):
    policy = PathPolicy(project_root=tmp_path)
    store = WorkflowStore(policy, tmp_path / "artifacts" / "state" / "workflow.sqlite3")
    target = tmp_path / "workspaces" / RUN_ID / "Model.bim"
    target.parent.mkdir(parents=True)
    target.write_bytes(RETA_BYTES)
    candidate = tmp_path / "artifacts" / RUN_ID / "candidate.bim"
    candidate.parent.mkdir(parents=True)
    return SimpleNamespace(
        policy=policy,
        store=store,
        workflow=ApprovalWorkflow(policy, store),
        target=target,
        candidate=candidate,
    )


def test_approved_measure_edit_is_applied_to_workspace_and_verified(workspace):
    edited = replace_measure_expression(load_reta(), *STRING_MEASURE, NEW_EXPRESSION)
    candidate_bytes = edited.to_bytes()
    write_bytes_atomically(workspace.candidate, candidate_bytes)
    workflow = workspace.workflow

    workflow.start_run(RUN_ID, "alice")
    workflow.submit(
        RUN_ID,
        "alice",
        base_sha256=sha256_hex(RETA_BYTES),
        candidate_sha256=sha256_hex(candidate_bytes),
        target_path=str(workspace.target),
        operation_summary={"edit": "replace_measure_expression", "measure": "TRX/_TRX_AMOUNT"},
    )
    workflow.approve(RUN_ID, "bob")
    outcome = workflow.apply(RUN_ID, "bob", workspace.candidate)
    state = workflow.record_verification(RUN_ID, "bob", passed=True, details={"check": "round-trip"})

    assert outcome is ApplyOutcome.WRITTEN
    written = json.loads(workspace.target.read_bytes())
    assert workspace.target.read_bytes() == candidate_bytes
    assert state is State.VERIFIED
    assert without_expression(written, *STRING_MEASURE) == without_expression(load_reta().data, *STRING_MEASURE)
