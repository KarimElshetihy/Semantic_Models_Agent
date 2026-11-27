"""DAX measure proposals: a valid draft is staged; every unsafe draft is refused before anything is written.

The model is MOCKED (ScriptedLlmClient). Each test uses a temporary project root with a copy of the RETA fixture
under tests/fixtures/, so the read policy applies as it does in the real project."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ssas_agent.approval import ApprovalWorkflow, WorkflowStore
from ssas_agent.bim.document import BimDocument
from ssas_agent.generation import (
    CandidateRefusedError,
    GenerationError,
    MeasureProposal,
    draft_measure,
    model_context,
    propose_measure,
)
from ssas_agent.llm import LlmError, ScriptedLlmClient
from ssas_agent.policy import PathPolicy
from ssas_agent.staging import ChangeStager

FIXTURE_BYTES = (Path(__file__).resolve().parents[1] / "fixtures" / "RETA_MODEL" / "Model.bim").read_bytes()
SOURCE = Path("tests/fixtures/RETA_MODEL/Model.bim")
RUN_ID = "run-measure-001"
REQUEST = "A measure that totals the transaction amount"
GOOD_FIELDS = {"table": "TRX", "measure_name": "Total Amount Check", "expression": "SUM(TRX[AMOUNT])"}


def reply(**fields) -> str:
    base = dict(GOOD_FIELDS)
    base.update(fields)
    return json.dumps(base)


@pytest.fixture
def project(tmp_path):
    source_file = tmp_path / SOURCE
    source_file.parent.mkdir(parents=True)
    source_file.write_bytes(FIXTURE_BYTES)
    policy = PathPolicy(project_root=tmp_path)
    store = WorkflowStore(policy, tmp_path / "artifacts" / "state" / "workflow.sqlite3")
    workflow = ApprovalWorkflow(policy, store)
    return SimpleNamespace(root=tmp_path, policy=policy, stager=ChangeStager(policy, workflow))


def written_paths(project):
    return {path.relative_to(project.root).as_posix() for path in project.root.rglob("*") if path.is_file()}


def propose_from_reply(project, reply_text, run_id=RUN_ID):
    data = BimDocument.from_bytes(FIXTURE_BYTES).data
    proposal = draft_measure(ScriptedLlmClient([reply_text]), REQUEST, data)
    return propose_measure(project.stager, project.policy, SOURCE, run_id, "alice", proposal)


def test_valid_draft_is_staged_and_the_source_model_is_unchanged(project):
    staged = propose_from_reply(project, reply())

    assert staged.workspace_model.exists()
    assert (project.root / SOURCE).read_bytes() == FIXTURE_BYTES
    assert "Total Amount Check" in (staged.review_folder / "diff.txt").read_text(encoding="utf-8")


def test_staged_candidate_contains_the_new_measure(project):
    staged = propose_from_reply(project, reply())

    candidate = BimDocument.from_bytes(staged.candidate_path.read_bytes()).data
    trx = next(table for table in candidate["model"]["tables"] if table["name"] == "TRX")
    assert any(measure["name"] == "Total Amount Check" for measure in trx["measures"])


def test_model_prompt_lists_the_tables_and_names_the_request(project):
    client = ScriptedLlmClient([reply()])
    data = BimDocument.from_bytes(FIXTURE_BYTES).data

    draft_measure(client, REQUEST, data)

    system_message, user_message = client.calls[0]
    assert "Table 'TRX'" in system_message.content
    assert "AMOUNT" in model_context(data)
    assert user_message.content == f"<<<REQUEST\n{REQUEST}\nREQUEST>>>"


def test_unknown_column_is_refused_and_nothing_is_written(project):
    before = written_paths(project)

    with pytest.raises(CandidateRefusedError, match="SC-020"):
        propose_from_reply(project, reply(expression="SUM(TRX[NO_SUCH_COLUMN])"))

    assert written_paths(project) == before


def test_unreadable_dax_is_refused_as_not_checked(project):
    with pytest.raises(CandidateRefusedError, match="not checked, so not staged"):
        propose_from_reply(project, reply(expression="SUM(TRX[AMOUNT)"))


def test_duplicate_measure_name_is_refused(project):
    with pytest.raises(CandidateRefusedError, match="already exists"):
        propose_from_reply(project, reply(measure_name="_TRX_AMOUNT"))


def test_unknown_table_is_refused(project):
    with pytest.raises(CandidateRefusedError):
        propose_from_reply(project, reply(table="NoSuchTable"))


def test_measure_name_with_square_brackets_is_refused_and_nothing_is_written(project):
    before = written_paths(project)

    with pytest.raises(CandidateRefusedError, match="must not contain '\\[' or '\\]'"):
        propose_from_reply(project, reply(measure_name="Total [Amount]"))

    assert written_paths(project) == before


def test_expression_starting_with_equals_is_refused_and_nothing_is_written(project):
    before = written_paths(project)

    with pytest.raises(CandidateRefusedError, match="must not start with '='"):
        propose_from_reply(project, reply(expression="=SUM(TRX[AMOUNT])"))

    assert written_paths(project) == before


def test_measure_name_with_a_dot_is_allowed_as_production_names_use_dots(project):
    staged = propose_from_reply(project, reply(measure_name="01.Total Amount"))

    candidate = BimDocument.from_bytes(staged.candidate_path.read_bytes()).data
    trx = next(table for table in candidate["model"]["tables"] if table["name"] == "TRX")
    assert any(measure["name"] == "01.Total Amount" for measure in trx["measures"])


@pytest.mark.parametrize("field", ["table", "measure_name", "expression"])
def test_blank_field_in_the_draft_is_refused(project, field):
    with pytest.raises(CandidateRefusedError, match="the draft has no"):
        propose_from_reply(project, reply(**{field: "   "}))


def test_bad_replies_are_retried_and_a_later_valid_reply_is_used():
    data = BimDocument.from_bytes(FIXTURE_BYTES).data
    client = ScriptedLlmClient(["not json", "[1, 2]", reply()])

    proposal = draft_measure(client, REQUEST, data)

    assert proposal.measure_name == "Total Amount Check"
    assert len(client.calls) == 3


def test_three_bad_replies_give_up_with_a_generation_error():
    data = BimDocument.from_bytes(FIXTURE_BYTES).data
    client = ScriptedLlmClient(["not json", "still not json", "[]"])

    with pytest.raises(GenerationError, match="no valid draft after 3 attempts"):
        draft_measure(client, REQUEST, data)


def test_unreachable_model_is_not_retried():
    data = BimDocument.from_bytes(FIXTURE_BYTES).data
    client = ScriptedLlmClient([])

    with pytest.raises(LlmError, match="no reply left"):
        draft_measure(client, REQUEST, data)


def test_proposal_is_a_plain_value_object():
    proposal = MeasureProposal(table_name="TRX", measure_name="X", expression="SUM(TRX[AMOUNT])")

    assert proposal.table_name == "TRX"
