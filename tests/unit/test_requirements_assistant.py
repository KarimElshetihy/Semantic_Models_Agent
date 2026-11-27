"""Requirements assistant tests. Model replies come from ScriptedLlmClient (MOCKED): no model is contacted.

Covers the template, the missing-definitions list, grounding of model drafts, your entries overriding drafts,
model failures recorded as notes, the Markdown output, and writing only into artifacts/."""

import json

import pytest

from ssas_agent.audit import RunRecorder
from ssas_agent.llm import ScriptedLlmClient
from ssas_agent.policy import PathPolicy
from ssas_agent.requirements import (
    FIELD_LABELS,
    FieldSource,
    RequirementEvent,
    RequirementField,
    RequirementsError,
    SPEC_FILE_NAME,
    build_spec,
    grounded_drafts,
    render_markdown,
    write_spec,
)

REQUEST = "Sales by region per month"
EXPECTED_FIELDS = [
    "business_objectives",
    "kpis",
    "data_sources",
    "table_grain",
    "keys",
    "refresh",
    "security",
    "target_ssas_version",
]


def model_reply(**fields) -> str:
    base = {field.value: "" for field in RequirementField}
    base.update(fields)
    return json.dumps(base)


def test_template_has_the_eight_fields_from_section_4_in_order():
    assert [field.value for field in RequirementField] == EXPECTED_FIELDS
    assert set(FIELD_LABELS) == set(RequirementField)


def test_request_without_a_model_leaves_every_field_missing():
    spec = build_spec(REQUEST)

    assert len(spec.missing_fields()) == 8
    assert all(spec.values[field].source is FieldSource.MISSING for field in RequirementField)


def test_empty_request_is_refused():
    with pytest.raises(RequirementsError, match="empty"):
        build_spec("   ")


def test_entered_values_are_marked_as_entered_by_the_user():
    spec = build_spec(REQUEST, user_values={RequirementField.KEYS: "Region Key"})

    assert spec.values[RequirementField.KEYS].text == "Region Key"
    assert spec.values[RequirementField.KEYS].source is FieldSource.USER
    assert RequirementField.KEYS not in spec.missing_fields()


def test_model_draft_fills_only_fields_the_request_supports():
    client = ScriptedLlmClient(
        [model_reply(kpis="Sales", table_grain="Region and month", keys="Customer churn")]
    )

    spec = build_spec(REQUEST, client=client)

    assert spec.values[RequirementField.KPIS].text == "Sales"
    assert spec.values[RequirementField.KPIS].source is FieldSource.DRAFTED_BY_MODEL
    assert spec.values[RequirementField.TABLE_GRAIN].source is FieldSource.DRAFTED_BY_MODEL


def test_ungrounded_draft_is_dropped_and_listed_as_missing():
    client = ScriptedLlmClient([model_reply(keys="Customer churn")])

    spec = build_spec(REQUEST, client=client)

    assert spec.values[RequirementField.KEYS].source is FieldSource.MISSING
    assert spec.dropped_drafts == (RequirementField.KEYS,)


def test_user_entry_overrides_a_model_draft():
    client = ScriptedLlmClient([model_reply(kpis="Sales")])

    spec = build_spec(
        REQUEST,
        client=client,
        user_values={RequirementField.KPIS: "Net sales amount"},
    )

    assert spec.values[RequirementField.KPIS].text == "Net sales amount"
    assert spec.values[RequirementField.KPIS].source is FieldSource.USER


def test_model_failure_is_noted_and_the_spec_is_still_built():
    client = ScriptedLlmClient(["this is not JSON"])

    spec = build_spec(REQUEST, client=client)

    assert spec.draft_note.startswith("model draft unavailable")
    assert len(spec.missing_fields()) == 8


def test_model_prompt_keeps_the_request_between_markers_and_forbids_invention():
    client = ScriptedLlmClient([model_reply()])

    build_spec(REQUEST, client=client)

    system_message, user_message = client.calls[0]
    assert "Never invent" in system_message.content
    assert user_message.content == f"<<<REQUEST\n{REQUEST}\nREQUEST>>>"


def test_grounded_drafts_keeps_only_drafts_whose_words_all_come_from_the_request():
    kept, dropped = grounded_drafts(
        {
            RequirementField.KPIS: "Sales",
            RequirementField.BUSINESS_OBJECTIVES: "Increase sales",
            RequirementField.KEYS: "Customer churn",
            RequirementField.REFRESH: "",
        },
        REQUEST,
    )

    assert kept == {RequirementField.KPIS: "Sales"}
    assert set(dropped) == {RequirementField.BUSINESS_OBJECTIVES, RequirementField.KEYS}


def test_draft_made_only_of_stop_words_is_dropped():
    kept, dropped = grounded_drafts({RequirementField.KEYS: "the and of"}, REQUEST)

    assert kept == {}
    assert dropped == (RequirementField.KEYS,)


def test_markdown_shows_each_value_with_its_source_and_lists_missing_definitions():
    client = ScriptedLlmClient([model_reply(kpis="Sales")])
    spec = build_spec(REQUEST, client=client, user_values={RequirementField.KEYS: "Region Key"})

    text = render_markdown(spec)

    assert "| Required KPIs | Sales | drafted by model |" in text
    assert "| Keys | Region Key | entered by user |" in text
    assert "| Target SSAS version | _not stated_ | missing |" in text
    assert "## Missing definitions" in text
    assert "- Target SSAS version" in text
    assert "must be reviewed before use" in text


def test_pipe_characters_and_line_breaks_in_values_do_not_break_the_table():
    spec = build_spec(REQUEST, user_values={RequirementField.DATA_SOURCES: "Oracle | SAP\nSecond line"})

    text = render_markdown(spec)

    assert "| Data sources | Oracle \\| SAP Second line | entered by user |" in text


def test_spec_is_written_only_into_the_run_artifacts_folder(tmp_path):
    policy = PathPolicy(project_root=tmp_path)
    recorder = RunRecorder(policy, tmp_path / "artifacts", "run-spec")
    spec = build_spec(REQUEST)

    path = write_spec(recorder, spec)

    assert path == tmp_path.resolve() / "artifacts" / "run-spec" / SPEC_FILE_NAME
    assert "## Missing definitions" in path.read_text(encoding="utf-8")
    assert not (tmp_path / "workspaces").exists()


def test_write_spec_records_counts_but_not_the_request_text(tmp_path):
    policy = PathPolicy(project_root=tmp_path)
    recorder = RunRecorder(policy, tmp_path / "artifacts", "run-spec-events")
    spec = build_spec("Confidential revenue plan for region X")

    write_spec(recorder, spec)

    events_text = (recorder.run_dir / "events.jsonl").read_text(encoding="utf-8")
    assert RequirementEvent.SPEC_WRITTEN in events_text
    assert '"missing_count": 8' in events_text
    assert "Confidential revenue plan" not in events_text
