"""Breaking-change classification tests (spec ENG-06).

The rule tests use synthetic changes. The comparison tests edit a copy of a fixture model in memory
and check the category that the real edit receives.
"""

import copy
import json
from pathlib import Path

import pytest

from ssas_agent.bim.document import BimDocument
from ssas_agent.diff import (
    ADDITIVE,
    BREAKING,
    COSMETIC,
    REVIEW,
    ObjectChange,
    SemanticDiff,
    classify_changes,
    compare_documents,
)
from ssas_agent.diff.classify import category_counts
from ssas_agent.diff.records import ADDED, CHANGED, REMOVED

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RETA_BYTES = (FIXTURES / "RETA_MODEL" / "Model.bim").read_bytes()


def changed(identity, properties=(), notes=()):
    return ObjectChange(identity, "column", CHANGED, tuple(properties), tuple(notes))


def classify_one(change):
    (item,) = classify_changes(SemanticDiff(changes=(change,)))
    return item


# --- rules on synthetic changes ----------------------------------------------------------------


def test_removed_object_is_breaking():
    item = classify_one(ObjectChange("measure:Sales/Total", "measure", REMOVED))

    assert (item.category, item.reasons) == (BREAKING, ("object removed",))


def test_added_object_is_additive():
    item = classify_one(ObjectChange("measure:Sales/Total", "measure", ADDED))

    assert (item.category, item.reasons) == (ADDITIVE, ("object added",))


@pytest.mark.parametrize("property_name", ["dataType", "fromTable", "fromColumn", "toTable", "toColumn"])
def test_data_type_and_relationship_endpoint_changes_are_breaking(property_name):
    assert classify_one(changed("column:Sales/Amount", [property_name])).category == BREAKING


@pytest.mark.parametrize("property_name", ["description", "displayFolder", "formatString", "annotations"])
def test_presentation_property_changes_are_cosmetic(property_name):
    assert classify_one(changed("column:Sales/Amount", [property_name])).category == COSMETIC


def test_expression_change_needs_review_not_breaking():
    item = classify_one(changed("measure:Sales/Total", ["expression"]))

    assert (item.category, item.reasons) == (REVIEW, ("expression changed",))


def test_fact_change_needs_review():
    assert classify_one(changed("role:Analysts", ["facts.member_count"])).category == REVIEW


@pytest.mark.parametrize("property_name", ["isActive", "cardinality", "crossFilteringBehavior", "isHidden", "unknownKey"])
def test_other_properties_default_to_review(property_name):
    assert classify_one(changed("relationship:R1", [property_name])).category == REVIEW


def test_storage_form_note_alone_is_cosmetic():
    item = classify_one(changed("measure:Sales/Total", notes=["expression form changed"]))

    assert (item.category, item.reasons) == (COSMETIC, ("expression form changed",))


def test_most_serious_category_wins_when_several_properties_change():
    item = classify_one(changed("column:Sales/Amount", ["description", "dataType"]))

    assert item.category == BREAKING
    assert sorted(item.reasons) == ["dataType changed", "description changed"]


def test_review_beats_cosmetic_when_both_change():
    item = classify_one(changed("measure:Sales/Total", ["description", "expression"]))

    assert item.category == REVIEW


def test_classified_changes_are_sorted_by_identity():
    diff = SemanticDiff(
        changes=(
            ObjectChange("measure:Z/Last", "measure", ADDED),
            ObjectChange("measure:A/First", "measure", ADDED),
        )
    )

    assert [item.change.identity for item in classify_changes(diff)] == ["measure:A/First", "measure:Z/Last"]


def test_category_counts_include_every_category_even_when_zero():
    counts = category_counts(classify_changes(SemanticDiff(changes=(ObjectChange("table:T", "table", ADDED),))))

    assert counts == {BREAKING: 0, REVIEW: 0, ADDITIVE: 1, COSMETIC: 0}


# --- comparison of real edits to a fixture model ------------------------------------------------


def edited_copy(modify):
    original = BimDocument.from_bytes(RETA_BYTES)
    data = copy.deepcopy(original.data)
    modify(data)
    return BimDocument(source_bytes=original.source_bytes, data=data, reproducible_on_load=True)


def compare(modify):
    return compare_documents(BimDocument.from_bytes(RETA_BYTES), edited_copy(modify), "Model.bim")


def first_table_with(data, key):
    return next(table for table in data["model"]["tables"] if table.get(key))


def first_column_with_data_type(data):
    for table in data["model"]["tables"]:
        for column in table.get("columns", []):
            if "dataType" in column:
                return table, column
    raise AssertionError("fixture has no column with a dataType")


def test_expression_edit_is_review_and_not_breaking():
    def edit(data):
        first_table_with(data, "measures")["measures"][0]["expression"] = "1 + 1"

    comparison = compare(edit)

    assert comparison.category_summary() == {BREAKING: 0, REVIEW: 1, ADDITIVE: 0, COSMETIC: 0}
    assert comparison.has_breaking_changes is False


def test_added_measure_is_additive():
    def edit(data):
        first_table_with(data, "measures")["measures"].append({"name": "_NEW", "expression": "1"})

    comparison = compare(edit)

    assert comparison.category_summary()[ADDITIVE] == 1
    assert comparison.has_breaking_changes is False


def test_renamed_measure_is_breaking_because_the_old_name_disappears():
    def edit(data):
        first_table_with(data, "measures")["measures"][0]["name"] = "Renamed Measure"

    comparison = compare(edit)

    assert comparison.has_breaking_changes is True
    assert comparison.category_summary() == {BREAKING: 1, REVIEW: 0, ADDITIVE: 1, COSMETIC: 0}


def test_data_type_change_is_breaking():
    def edit(data):
        _, column = first_column_with_data_type(data)
        column["dataType"] = "dateTime" if column["dataType"] != "dateTime" else "int64"

    comparison = compare(edit)

    assert comparison.has_breaking_changes is True
    assert comparison.classified[0].category == BREAKING


def test_removed_relationship_is_breaking():
    def edit(data):
        data["model"]["relationships"] = data["model"]["relationships"][1:]

    comparison = compare(edit)

    assert comparison.has_breaking_changes is True
    assert comparison.category_summary()[BREAKING] == 1


def test_description_edit_is_cosmetic():
    def edit(data):
        first_table_with(data, "measures")["measures"][0]["description"] = "Shown to report users"

    comparison = compare(edit)

    assert comparison.category_summary() == {BREAKING: 0, REVIEW: 0, ADDITIVE: 0, COSMETIC: 1}
    assert comparison.has_breaking_changes is False


def test_identical_documents_have_no_changes():
    comparison = compare(lambda data: None)

    assert comparison.classified == ()
    assert comparison.text_diff == ""


def test_payload_has_categories_and_names_but_no_expression_text():
    secret_expression = "SUM('Secret'[Value]) * 987654"

    def edit(data):
        first_table_with(data, "measures")["measures"][0]["expression"] = secret_expression

    payload = compare(edit).to_payload()
    serialized = json.dumps(payload)

    assert payload["categories"] == {BREAKING: 0, REVIEW: 1, ADDITIVE: 0, COSMETIC: 0}
    assert payload["changes"][0]["category"] == REVIEW
    assert secret_expression not in serialized
    assert "987654" not in serialized
