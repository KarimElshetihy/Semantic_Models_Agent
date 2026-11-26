"""Phase 0 semantic diff tests on the sanitized fixtures and small synthetic models."""

import copy
from pathlib import Path

from ssas_agent.bim import load_bim_file
from ssas_agent.diff import ADDED, CHANGED, REMOVED, diff_inventories
from ssas_agent.inventory import build_inventory

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
FORM_CHANGED = ("expression form changed",)


def fixture_document(project):
    return copy.deepcopy(load_bim_file(FIXTURES_ROOT / project / "Model.bim").data)


def diff_documents(before_document, after_document):
    return diff_inventories(build_inventory(before_document), build_inventory(after_document))


def minimal_document(tables=(), **model_extras):
    return {"name": "SemanticModel", "compatibilityLevel": 1500, "model": {"tables": list(tables), **model_extras}}


def first_measure(document):
    for table in document["model"]["tables"]:
        if table.get("measures"):
            return table, table["measures"][0]
    raise AssertionError("fixture has no measures")


def append_to_expression(measure, suffix):
    expression = measure["expression"]
    if isinstance(expression, list):
        measure["expression"] = expression + [suffix]
    else:
        measure["expression"] = expression + suffix


def test_identical_documents_produce_empty_diff():
    diff = diff_documents(fixture_document("MOF_MODEL"), fixture_document("MOF_MODEL"))

    assert diff.is_empty
    assert diff.summary() == {ADDED: 0, REMOVED: 0, CHANGED: 0}


def test_measure_expression_edit_is_the_only_change():
    before = fixture_document("MOF_MODEL")
    after = copy.deepcopy(before)
    table, measure = first_measure(after)
    append_to_expression(measure, " + 0")

    diff = diff_documents(before, after)

    assert [(change.identity, change.change_kind) for change in diff.changes] == [
        (f"measure:{table['name']}/{measure['name']}", CHANGED),
    ]
    assert diff.changes[0].changed_properties == ("expression",)
    assert diff.changes[0].notes == ()


def test_changed_property_is_reported_by_name():
    before = fixture_document("MOF_MODEL")
    after = copy.deepcopy(before)
    table, measure = first_measure(after)
    measure["formatString"] = "#,0.00 test-format"

    change = diff_documents(before, after).changes[0]

    assert change.identity == f"measure:{table['name']}/{measure['name']}"
    assert change.changed_properties == ("formatString",)


def test_new_column_is_added():
    before = fixture_document("RETA_MODEL")
    after = copy.deepcopy(before)
    table = after["model"]["tables"][0]
    table["columns"].append({"name": "NewColumn", "dataType": "string", "sourceColumn": "NewColumn"})

    diff = diff_documents(before, after)

    assert [(change.identity, change.change_kind) for change in diff.changes] == [
        (f"column:{table['name']}/NewColumn", ADDED),
    ]


def test_removed_relationship_is_reported():
    before = fixture_document("RETA_MODEL")
    after = copy.deepcopy(before)
    removed = after["model"]["relationships"].pop(0)

    diff = diff_documents(before, after)

    assert [(change.identity, change.change_kind) for change in diff.changes] == [
        (f"relationship:{removed['name']}", REMOVED),
    ]


def test_renamed_table_appears_as_removed_and_added():
    before = minimal_document(tables=[{"name": "Sales", "columns": [{"name": "Amount"}]}])
    after = minimal_document(tables=[{"name": "Revenue", "columns": [{"name": "Amount"}]}])

    diff = diff_documents(before, after)

    assert diff.summary() == {ADDED: 2, REMOVED: 2, CHANGED: 0}
    assert {change.identity for change in diff.of_kind(REMOVED)} == {"table:Sales", "column:Sales/Amount"}
    assert {change.identity for change in diff.of_kind(ADDED)} == {"table:Revenue", "column:Revenue/Amount"}


def test_expression_storage_form_change_is_a_note_not_an_expression_change():
    before = minimal_document(tables=[{"name": "T", "measures": [{"name": "Total", "expression": "SUM(T[x])"}]}])
    after = minimal_document(tables=[{"name": "T", "measures": [{"name": "Total", "expression": ["SUM(T[x])"]}]}])

    changes = diff_documents(before, after).changes

    assert len(changes) == 1
    assert changes[0].change_kind == CHANGED
    assert changes[0].changed_properties == ()
    assert changes[0].notes == FORM_CHANGED


def test_credential_change_alone_is_not_a_model_change():
    before = fixture_document("MOF_MODEL")
    after = copy.deepcopy(before)
    after["model"]["dataSources"][0]["credential"]["Username"] = "someone_else"

    assert diff_documents(before, after).is_empty


def test_role_member_count_change_is_reported_as_fact():
    before = fixture_document("MOF_MODEL")
    after = copy.deepcopy(before)
    role = after["model"]["roles"][0]
    role.setdefault("members", []).append({"memberName": "Test Member"})

    changes = diff_documents(before, after).changes

    assert [(change.identity, change.changed_properties) for change in changes] == [
        (f"role:{role['name']}", ("facts.member_count",)),
    ]
