"""New model from a JSON spec (step 8): a valid spec builds a checked candidate; every other spec is refused.

No model is read from examples and no database is contacted. Each writer test uses a temporary project
root, so the write policy applies as it does in the real project."""

import json
import re
from pathlib import Path

import pytest

from ssas_agent.bim.document import BimDocument, serialize_visual_studio_bytes
from ssas_agent.newmodel import (
    NewModelRefusedError,
    SpecError,
    build_model_document,
    create_new_model,
    parse_spec_text,
    project_file_text,
    read_spec_file,
)
from ssas_agent.newmodel.build import relationship_name
from ssas_agent.newmodel.spec import DataType
from ssas_agent.policy import Operation
from ssas_agent.policy import PathPolicy
from ssas_agent.validation import run_static_checks

PROJECT_GUID = "8CE414BB-95B2-4C99-9E03-51BA72086E22"
RUN_ID = "run-new-model-001"
POWER_QUERY = 'let\n    Source = Oracle.Database("oracle-host:1521/oracle_service"),\nin\n    Source'
SERVER_PLACEHOLDER = "<set in Visual Studio>"
GUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def sample_spec() -> dict:
    return {
        "spec_version": 1,
        "project_name": "SAMPLE_SALES",
        "compatibility_level": 1500,
        "culture": "en-US",
        "data_source": {"name": "Oracle sample", "kind": "oracle", "server": SERVER_PLACEHOLDER},
        "tables": [
            {
                "name": "FACT_SALES",
                "grain": "one row per sale line",
                "power_query": POWER_QUERY,
                "columns": [
                    {"name": "SALE_ID", "data_type": "int64", "is_key": True},
                    {"name": "CUSTOMER_ID", "data_type": "int64"},
                    {"name": "AMOUNT", "data_type": "decimal", "source_column": "SALE_AMOUNT"},
                ],
            },
            {
                "name": "DIM_CUSTOMER",
                "grain": "one row per customer",
                "power_query": None,
                "columns": [
                    {"name": "CUSTOMER_ID", "data_type": "int64", "is_key": True},
                    {"name": "CUSTOMER_NAME", "data_type": "string"},
                ],
            },
        ],
        "relationships": [
            {"from_table": "FACT_SALES", "from_column": "CUSTOMER_ID",
             "to_table": "DIM_CUSTOMER", "to_column": "CUSTOMER_ID"}
        ],
        "measures": [
            {"table": "FACT_SALES", "name": "Total Sales",
             "expression": "SUM(FACT_SALES[AMOUNT])", "kpi": "Total sales"}
        ],
    }


def spec_text_after(change) -> str:
    spec = sample_spec()
    change(spec)
    return json.dumps(spec)


@pytest.fixture
def project(tmp_path):
    return PathPolicy(project_root=tmp_path)


def written_paths(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def test_valid_spec_parses_into_typed_objects():
    spec = parse_spec_text(json.dumps(sample_spec()))

    assert spec.project_name == "SAMPLE_SALES"
    assert [table.name for table in spec.tables] == ["FACT_SALES", "DIM_CUSTOMER"]
    fact_columns = {column.name: column for column in spec.tables[0].columns}
    assert fact_columns["SALE_ID"].data_type is DataType.INT64
    assert fact_columns["SALE_ID"].is_key is True
    assert fact_columns["CUSTOMER_ID"].source_column == "CUSTOMER_ID"
    assert fact_columns["AMOUNT"].source_column == "SALE_AMOUNT"
    assert spec.tables[1].power_query is None


def test_culture_defaults_to_en_us_when_missing():
    spec = parse_spec_text(spec_text_after(lambda raw: raw.pop("culture")))

    assert spec.culture == "en-US"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda raw: raw.update(compatibility_level=1400), "compatibility_level must be 1500"),
        (lambda raw: raw.update(spec_version=2), "spec_version must be 1"),
        (lambda raw: raw.update(project_name="../evil"), "project_name must start with a letter"),
        (lambda raw: raw["data_source"].update(kind="sqlserver"), "kind must be 'oracle'"),
        (lambda raw: raw.update(extra="x"), "unknown key(s): extra"),
        (lambda raw: raw["tables"][0]["columns"][0].update(data_type="money"), "must be one of"),
        (lambda raw: raw["tables"][0]["columns"][0].update(is_key="yes"), "must be true or false"),
        (lambda raw: raw.update(tables=[]), "at least one table"),
        (lambda raw: raw["tables"].append({**raw["tables"][1], "name": "dim_customer"}), "used more than once"),
        (
            lambda raw: raw["relationships"].__setitem__(
                0, {**raw["relationships"][0], "to_column": "NO_SUCH"}
            ),
            "column 'DIM_CUSTOMER[NO_SUCH]' is not in the spec",
        ),
        (lambda raw: raw["measures"][0].update(table="NOPE"), "table 'NOPE' is not in the spec"),
        (lambda raw: raw["measures"][0].update(name="Total [Sales]"), "must not contain '[' or ']'"),
        (lambda raw: raw["measures"][0].update(expression="=SUM(FACT_SALES[AMOUNT])"), "must not start with '='"),
        (
            lambda raw: raw["measures"].append({**raw["measures"][0], "name": "total sales"}),
            "used more than once",
        ),
    ],
)
def test_bad_specs_are_refused_with_the_reason(change, expected):
    with pytest.raises(SpecError, match=re.escape(expected)):
        parse_spec_text(spec_text_after(change))


def test_credential_key_is_refused_and_its_value_is_not_shown():
    def add_password(raw):
        raw["data_source"]["password"] = "SuperSecret123"

    with pytest.raises(SpecError) as error:
        parse_spec_text(spec_text_after(add_password))

    message = str(error.value)
    assert "data_source.password looks like a credential" in message
    assert "SuperSecret123" not in message


def test_invalid_json_is_refused_with_its_position():
    with pytest.raises(SpecError, match="not valid JSON"):
        parse_spec_text("{")


def test_built_model_has_compatibility_1500_and_no_credential():
    spec = parse_spec_text(json.dumps(sample_spec()))

    document = build_model_document(spec)

    assert document["compatibilityLevel"] == 1500
    source = document["model"]["dataSources"][0]
    assert "credential" not in source
    assert source["connectionDetails"]["address"]["server"] == SERVER_PLACEHOLDER


def test_multi_line_power_query_is_stored_as_lines_and_one_line_measure_as_text():
    document = build_model_document(parse_spec_text(json.dumps(sample_spec())))

    fact = document["model"]["tables"][0]
    assert fact["partitions"][0]["source"]["expression"] == POWER_QUERY.split("\n")
    assert fact["measures"][0]["expression"] == "SUM(FACT_SALES[AMOUNT])"


def test_table_without_power_query_has_no_partition():
    document = build_model_document(parse_spec_text(json.dumps(sample_spec())))

    dimension = document["model"]["tables"][1]
    assert "partitions" not in dimension


def test_relationship_names_are_stable_guids():
    spec = parse_spec_text(json.dumps(sample_spec()))
    relationship = spec.relationships[0]

    name = relationship_name(relationship)

    assert name == relationship_name(relationship)
    assert GUID_PATTERN.fullmatch(name)


def test_built_model_round_trips_byte_for_byte():
    document = build_model_document(parse_spec_text(json.dumps(sample_spec())))

    raw = serialize_visual_studio_bytes(document)

    assert BimDocument.from_bytes(raw).reproducible_on_load is True


def test_built_model_passes_the_static_checks():
    document = build_model_document(parse_spec_text(json.dumps(sample_spec())))

    report = run_static_checks(document)

    assert report.has_errors is False


def test_project_file_lists_the_model_and_has_no_user_or_server_settings():
    text = project_file_text("SAMPLE_SALES", PROJECT_GUID)

    assert '<Compile Include="Model.bim">' in text
    assert f"<ProjectGuid>{{{PROJECT_GUID}}}</ProjectGuid>" in text
    assert "<Name>SAMPLE_SALES</Name>" in text
    assert "DeploymentServer" not in text
    assert "Karim" not in text
    assert "\r\n" in text
    assert text.count("\n") == text.count("\r\n")


def test_candidate_files_are_written_to_workspaces_only(tmp_path, project):
    candidate = create_new_model(
        project, parse_spec_text(json.dumps(sample_spec())), RUN_ID, project_guid=PROJECT_GUID
    )

    workspace = tmp_path / "workspaces" / RUN_ID / "SAMPLE_SALES"
    assert candidate.model_path == workspace / "Model.bim"
    assert candidate.project_path == workspace / "SAMPLE_SALES.smproj"
    assert candidate.model_path.exists() and candidate.project_path.exists()
    assert candidate.mapping_path == tmp_path / "artifacts" / RUN_ID / "mapping.json"
    assert BimDocument.from_bytes(candidate.model_path.read_bytes()).reproducible_on_load is True


def test_mapping_lists_the_kpis_and_leaves_out_power_query_and_server(tmp_path, project):
    candidate = create_new_model(
        project, parse_spec_text(json.dumps(sample_spec())), RUN_ID, project_guid=PROJECT_GUID
    )

    mapping_text = candidate.mapping_path.read_text(encoding="utf-8")

    mapping = json.loads(mapping_text)
    assert mapping["measures"] == [{"table": "FACT_SALES", "name": "Total Sales", "kpi": "Total sales"}]
    assert mapping["tables"][0]["partition"] == "present"
    assert mapping["tables"][1]["partition"] == "none"
    assert "Oracle.Database" not in mapping_text
    assert SERVER_PLACEHOLDER not in mapping_text


def test_refused_model_writes_nothing(tmp_path, project):
    before = written_paths(tmp_path)
    bad_spec = parse_spec_text(
        spec_text_after(lambda raw: raw["measures"][0].update(expression="SUM(FACT_SALES[NO_SUCH])"))
    )

    with pytest.raises(NewModelRefusedError, match="SC-020"):
        create_new_model(project, bad_spec, RUN_ID, project_guid=PROJECT_GUID)

    assert written_paths(tmp_path) == before


def test_existing_output_folder_is_never_overwritten(tmp_path, project):
    spec = parse_spec_text(json.dumps(sample_spec()))
    create_new_model(project, spec, RUN_ID, project_guid=PROJECT_GUID)
    model_bytes = (tmp_path / "workspaces" / RUN_ID / "SAMPLE_SALES" / "Model.bim").read_bytes()

    with pytest.raises(NewModelRefusedError, match="already exists"):
        create_new_model(project, spec, RUN_ID, project_guid=PROJECT_GUID)

    assert (tmp_path / "workspaces" / RUN_ID / "SAMPLE_SALES" / "Model.bim").read_bytes() == model_bytes


def test_invalid_run_id_is_refused(project):
    with pytest.raises(ValueError):
        create_new_model(project, parse_spec_text(json.dumps(sample_spec())), "../escape", project_guid=PROJECT_GUID)


def test_data_type_names_match_tmsl():
    assert {member.value for member in DataType} == {
        "string", "int64", "decimal", "double", "boolean", "dateTime",
    }


def test_specs_folder_is_readable_but_not_writable(project):
    assert project.decide(Operation.READ, "specs/sample.json").allowed
    assert not project.decide(Operation.WRITE, "specs/sample.json").allowed


def test_spec_file_in_specs_folder_is_read_through_the_policy(tmp_path, project):
    spec_file = tmp_path / "specs" / "sample.json"
    spec_file.parent.mkdir()
    spec_file.write_bytes(json.dumps(sample_spec()).encode("utf-8-sig"))

    spec = parse_spec_text(read_spec_file(project, Path("specs/sample.json")))

    assert spec.project_name == "SAMPLE_SALES"


def test_spec_file_outside_readable_folders_is_refused(tmp_path, project):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "spec.json").write_text(json.dumps(sample_spec()), encoding="utf-8")

    with pytest.raises(PermissionError):
        read_spec_file(project, Path("notes/spec.json"))


def test_missing_spec_file_is_reported_without_a_traceback(tmp_path, project):
    (tmp_path / "specs").mkdir()

    with pytest.raises(SpecError, match="cannot be read: missing.json"):
        read_spec_file(project, Path("specs/missing.json"))


def test_spec_file_that_is_not_utf8_is_refused(tmp_path, project):
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "binary.json").write_bytes(b"\xff\xfe\x00\x01")

    with pytest.raises(SpecError, match="not UTF-8 text: binary.json"):
        read_spec_file(project, Path("specs/binary.json"))