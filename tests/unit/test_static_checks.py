"""Static check tests. Each small model plants one defect, so a rule is proven to catch it and stay quiet otherwise.

The fixture tests at the end run the checks on the sanitized example models. Their expected results
are the reviewed results from the example projects, not an assumption.
"""

import json
from pathlib import Path

import pytest

from ssas_agent.validation import ERROR, WARNING, run_static_checks

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def make_column(name, expression=None, column_type=None):
    column = {"name": name}
    if column_type is not None:
        column["type"] = column_type
    if expression is not None:
        column["expression"] = expression
    return column


def make_measure(name, expression="1"):
    return {"name": name, "expression": expression}


def make_table(name, columns=(), measures=(), partitions=()):
    return {"name": name, "columns": list(columns), "measures": list(measures), "partitions": list(partitions)}


def make_relationship(name, from_table, from_column, to_table, to_column):
    return {
        "name": name,
        "fromTable": from_table,
        "fromColumn": from_column,
        "toTable": to_table,
        "toColumn": to_column,
    }


def make_model(tables=(), relationships=(), roles=()):
    model = {"tables": list(tables), "relationships": list(relationships)}
    if roles:
        model["roles"] = list(roles)
    return {"model": model}


def rule_ids(report):
    return [finding.rule_id for finding in report.findings]


def finding_for(report, rule_id):
    matches = [finding for finding in report.findings if finding.rule_id == rule_id]
    assert len(matches) == 1, f"expected one {rule_id}, got {rule_ids(report)}"
    return matches[0]


def clean_model():
    sales = make_table(
        "Sales",
        columns=[make_column("SalesKey"), make_column("Amount"), make_column("Margin", "[Amount] * 0.2", "calculated")],
        measures=[make_measure("Total Amount", "SUM(Sales[Amount])")],
    )
    customer = make_table("Customer", columns=[make_column("CustomerKey")])
    relationship = make_relationship("Sales_Customer", "Sales", "SalesKey", "Customer", "CustomerKey")
    return make_model([sales, customer], [relationship])


# --- clean model and report shape -------------------------------------------------------------


def test_clean_model_has_no_findings_and_no_errors():
    report = run_static_checks(clean_model())

    assert report.findings == ()
    assert report.has_errors is False


def test_warning_alone_does_not_count_as_an_error():
    model = make_model([make_table("Sales", measures=[make_measure("Empty", "")])])

    report = run_static_checks(model)

    assert rule_ids(report) == ["SC-040"]
    assert report.findings[0].severity == WARNING
    assert report.has_errors is False


def test_report_payload_lists_counts_findings_and_not_checked_items():
    model = make_model([make_table("Sales", columns=[make_column("Empty", None, "calculated")])])

    payload = run_static_checks(model).to_payload()

    assert payload["counts"] == {"error": 1, "warning": 0}
    assert payload["findings"][0]["rule_id"] == "SC-030"
    assert payload["findings"][0]["identity"] == "column:Sales/Empty"
    assert payload["not_checked"] == []


def test_results_are_identical_on_repeated_runs():
    model = make_model(
        [make_table("Sales", columns=[make_column("A", None, "calculated")], measures=[make_measure("M", "")])]
    )

    assert run_static_checks(model).to_payload() == run_static_checks(model).to_payload()


# --- SC-001 to SC-004: duplicate names ----------------------------------------------------------


def test_duplicate_table_names_are_reported():
    model = make_model([make_table("Sales"), make_table("Sales")])

    finding = finding_for(run_static_checks(model), "SC-001")

    assert finding.identity == "table:Sales"
    assert finding.severity == ERROR


def test_table_names_differing_only_in_case_are_duplicates():
    model = make_model([make_table("Sales"), make_table("sales")])

    assert finding_for(run_static_checks(model), "SC-001").evidence == "2 tables named 'Sales'"


def test_duplicate_column_in_one_table_is_reported():
    model = make_model([make_table("Sales", columns=[make_column("Amount"), make_column("Amount")])])

    assert finding_for(run_static_checks(model), "SC-002").identity == "column:Sales/Amount"


def test_duplicate_measure_in_one_table_is_reported():
    model = make_model([make_table("Sales", measures=[make_measure("Total"), make_measure("Total")])])

    assert finding_for(run_static_checks(model), "SC-003").identity == "measure:Sales/Total"


def test_same_column_name_in_two_tables_is_not_a_duplicate():
    model = make_model([make_table("Sales", columns=[make_column("Key")]), make_table("Customer", columns=[make_column("Key")])])

    assert rule_ids(run_static_checks(model)) == []


def test_duplicate_relationship_names_are_reported():
    relationship = make_relationship("Link", "Sales", "A", "Customer", "B")
    model = make_model(
        [make_table("Sales", columns=[make_column("A")]), make_table("Customer", columns=[make_column("B")])],
        [relationship, dict(relationship)],
    )

    assert finding_for(run_static_checks(model), "SC-004").identity == "relationship:Link"


# --- SC-006: objects without names -------------------------------------------------------------


@pytest.mark.parametrize(
    "model, identity",
    [
        (make_model([{"columns": [], "measures": []}]), "table:(unnamed #0)"),
        (make_model([make_table("Sales", columns=[{"type": None}])]), "column:Sales/(unnamed #0)"),
        (make_model([make_table("Sales", measures=[{"expression": "1"}])]), "measure:Sales/(unnamed #0)"),
        (
            make_model(
                [make_table("Sales", columns=[make_column("A")]), make_table("Customer", columns=[make_column("B")])],
                [{"fromTable": "Sales", "fromColumn": "A", "toTable": "Customer", "toColumn": "B"}],
            ),
            "relationship:(unnamed #0)",
        ),
    ],
)
def test_objects_without_names_are_reported(model, identity):
    assert finding_for(run_static_checks(model), "SC-006").identity == identity


# --- SC-010: relationships ---------------------------------------------------------------------


def test_relationship_to_missing_column_is_reported_with_the_side():
    model = make_model(
        [make_table("Sales", columns=[make_column("CustomerKey")]), make_table("Customer", columns=[make_column("Id")])],
        [make_relationship("Sales_Customer", "Sales", "CustomerKey", "Customer", "CustomerKey")],
    )

    finding = finding_for(run_static_checks(model), "SC-010")

    assert finding.identity == "relationship:Sales_Customer"
    assert finding.evidence == "to side Customer[CustomerKey] does not exist"


def test_relationship_to_missing_table_is_reported():
    model = make_model(
        [make_table("Sales", columns=[make_column("CustomerKey")])],
        [make_relationship("Broken", "Sales", "CustomerKey", "Ghost", "Id")],
    )

    assert finding_for(run_static_checks(model), "SC-010").evidence == "to side Ghost[Id] does not exist"


def test_relationship_columns_are_matched_ignoring_case():
    model = make_model(
        [make_table("Sales", columns=[make_column("CustomerKey")]), make_table("customer", columns=[make_column("customerkey")])],
        [make_relationship("Sales_Customer", "Sales", "CustomerKey", "Customer", "CustomerKey")],
    )

    assert rule_ids(run_static_checks(model)) == []


# --- SC-020 and SC-021: DAX references ----------------------------------------------------------


def test_qualified_reference_to_missing_table_is_reported():
    model = make_model([make_table("Sales", measures=[make_measure("Bad", "SUM(Ghost[Amount])")])])

    finding = finding_for(run_static_checks(model), "SC-020")

    assert finding.identity == "measure:Sales/Bad"
    assert finding.evidence == "Ghost[Amount]: table 'Ghost' does not exist"


def test_qualified_reference_to_missing_column_is_reported():
    model = make_model(
        [make_table("Sales", columns=[make_column("Amount")]), make_table("Customer", measures=[make_measure("Bad", "SUM(Sales[Price])")])]
    )

    assert finding_for(run_static_checks(model), "SC-020").evidence == "Sales[Price]: 'Sales' has no column or measure 'Price'"


def test_qualified_reference_to_a_measure_of_that_table_is_accepted():
    model = make_model(
        [make_table("Sales", measures=[make_measure("Total", "1"), make_measure("Double", "'Sales'[Total] * 2")])]
    )

    assert rule_ids(run_static_checks(model)) == []


def test_unqualified_reference_matching_nothing_is_reported():
    model = make_model([make_table("Sales", measures=[make_measure("Bad", "[Missing] + 1")])])

    finding = finding_for(run_static_checks(model), "SC-021")

    assert finding.evidence == "[Missing]: no measure or column named 'Missing' in this table or the model"


def test_unqualified_column_of_own_table_in_calculated_column_is_accepted():
    model = make_model([make_table("Sales", columns=[make_column("Amount"), make_column("Margin", "[Amount] * 2", "calculated")])])

    assert rule_ids(run_static_checks(model)) == []


def test_unqualified_measure_from_another_table_is_accepted():
    model = make_model(
        [make_table("Sales", measures=[make_measure("Total", "1")]), make_table("Report", measures=[make_measure("Share", "[Total] / 2")])]
    )

    assert rule_ids(run_static_checks(model)) == []


def test_table_reference_is_matched_ignoring_case():
    model = make_model(
        [make_table("datefiltertype", columns=[make_column("Type")]), make_table("Report", measures=[make_measure("Pick", "SELECTEDVALUE(DateFilterType[Type])")])]
    )

    assert rule_ids(run_static_checks(model)) == []


def test_reference_inside_a_string_literal_is_not_reported():
    model = make_model([make_table("Sales", measures=[make_measure("Label", 'FORMAT(1, "Ghost[Missing]")')])])

    assert rule_ids(run_static_checks(model)) == []


def test_expression_the_scanner_cannot_read_is_listed_as_not_checked():
    model = make_model([make_table("Sales", measures=[make_measure("Odd", "SUM(Sales[Amount)")])])

    report = run_static_checks(model)

    assert report.findings == ()
    assert [(item.identity, item.reason) for item in report.not_checked] == [
        ("measure:Sales/Odd", "unbalanced brackets"),
    ]


# --- SC-030 and SC-040: empty expressions -------------------------------------------------------


def test_calculated_column_without_expression_is_an_error():
    model = make_model([make_table("Sales", columns=[make_column("Add Column2", None, "calculated")])])

    finding = finding_for(run_static_checks(model), "SC-030")

    assert finding.identity == "column:Sales/Add Column2"
    assert finding.severity == ERROR


def test_calculated_column_with_blank_expression_is_an_error():
    model = make_model([make_table("Sales", columns=[make_column("Blank", "   ", "calculated")])])

    assert rule_ids(run_static_checks(model)) == ["SC-030"]


def test_plain_column_without_expression_is_not_reported():
    model = make_model([make_table("Sales", columns=[make_column("Plain")])])

    assert rule_ids(run_static_checks(model)) == []


def test_calculated_table_column_is_not_reported_as_empty():
    model = make_model([make_table("Sales", columns=[make_column("FromTable", None, "calculatedTableColumn")])])

    assert rule_ids(run_static_checks(model)) == []


@pytest.mark.parametrize("measure", [make_measure("NoExpression", ""), {"name": "MissingKey"}])
def test_blank_or_missing_measure_expression_is_a_warning(measure):
    model = make_model([make_table("Sales", measures=[measure])])

    finding = finding_for(run_static_checks(model), "SC-040")

    assert finding.severity == WARNING


# --- scope notes -------------------------------------------------------------------------------


def test_partitions_and_roles_are_listed_as_not_checked():
    model = make_model(
        [make_table("Sales", partitions=[{"name": "Sales", "source": {"type": "m"}}])],
        roles=[{"name": "Analysts"}],
    )

    identities = [item.identity for item in run_static_checks(model).not_checked]

    assert identities == ["partitions", "roles"]


def test_scope_notes_are_absent_when_there_is_nothing_to_note():
    assert run_static_checks(make_model([make_table("Sales")])).not_checked == ()


# --- example models (sanitized) ----------------------------------------------------------------


def load_fixture(project_name):
    return json.loads((FIXTURES / project_name / "Model.bim").read_bytes().decode("utf-8-sig"))


@pytest.mark.parametrize("project_name", ["EOPM_MODEL", "HISTORICAL_COLLECTION_VS_PAYMENT_MODEL", "MOF_MODEL", "RETA_MODEL"])
def test_fixture_expressions_are_all_read_without_scanner_problems(project_name):
    report = run_static_checks(load_fixture(project_name))

    assert all(item.identity in ("partitions", "roles") for item in report.not_checked)


def test_historical_model_reports_the_known_empty_calculated_column():
    report = run_static_checks(load_fixture("HISTORICAL_COLLECTION_VS_PAYMENT_MODEL"))

    assert [(finding.rule_id, finding.identity) for finding in report.findings] == [
        ("SC-030", "column:EPAY/Add Column2"),
    ]
    assert report.has_errors is True


@pytest.mark.parametrize("project_name", ["EOPM_MODEL", "MOF_MODEL", "RETA_MODEL"])
def test_other_fixture_models_have_no_findings(project_name):
    assert run_static_checks(load_fixture(project_name)).findings == ()
