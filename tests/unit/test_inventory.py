"""Phase 0 inventory tests on the sanitized fixtures.

Expected headline numbers come from docs/PHASE0_DESIGN.md section 2. Every
other count is recomputed from the raw JSON here, so the inventory is checked
against an independent count rather than against itself.
"""

import json
from pathlib import Path

import pytest

from ssas_agent.bim import load_bim_file
from ssas_agent.inventory import InventoryError, build_inventory

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_MODELS = sorted(FIXTURES_ROOT.rglob("Model.bim"))

HEADLINE_COUNTS = {
    "EOPM_MODEL": {"table": 17, "column": 150, "calculated": 2, "measure": 0, "relationship": 18, "role": 0},
    "HISTORICAL_COLLECTION_VS_PAYMENT_MODEL": {
        "table": 28, "column": 351, "calculated": 20, "measure": 10, "relationship": 65, "role": 0,
    },
    "MOF_MODEL": {"table": 19, "column": 187, "calculated": 7, "measure": 32, "relationship": 23, "role": 6},
    "RETA_MODEL": {"table": 8, "column": 111, "calculated": 2, "measure": 4, "relationship": 9, "role": 0},
}

M_SHAPE_COUNTS = {
    "EOPM_MODEL": {"native_query_only": 15, "native_query_plus_steps": 1, "no_native_query": 1},
    "HISTORICAL_COLLECTION_VS_PAYMENT_MODEL": {"native_query_only": 27},
    "MOF_MODEL": {"native_query_only": 20, "no_native_query": 1},
    "RETA_MODEL": {"native_query_only": 7, "no_native_query": 1},
}


def project_name(model_path):
    return model_path.parent.name


def load_model_document(model_path):
    return load_bim_file(model_path).data


def inventory_for(model_path):
    return build_inventory(load_model_document(model_path))


def raw_object_counts(document):
    model = document["model"]
    tables = model.get("tables", [])
    return {
        "table": len(tables),
        "column": sum(len(table.get("columns", [])) for table in tables),
        "measure": sum(len(table.get("measures", [])) for table in tables),
        "partition": sum(len(table.get("partitions", [])) for table in tables),
        "relationship": len(model.get("relationships", [])),
        "role": len(model.get("roles", [])),
        "role_permission": sum(len(role.get("tablePermissions", [])) for role in model.get("roles", [])),
        "data_source": len(model.get("dataSources", [])),
    }


def calculated_column_count(inventory):
    columns = inventory.items_of_type("column")
    return sum(column.properties.get("type") == "calculated" for column in columns)


def minimal_document(tables=(), **model_extras):
    return {"name": "SemanticModel", "compatibilityLevel": 1500, "model": {"tables": list(tables), **model_extras}}


@pytest.mark.parametrize("model_path", FIXTURE_MODELS, ids=project_name)
def test_headline_counts_match_design_document(model_path):
    inventory = inventory_for(model_path)
    counts = inventory.count_by_type()
    expected = HEADLINE_COUNTS[project_name(model_path)]

    assert counts.get("table", 0) == expected["table"]
    assert counts.get("column", 0) == expected["column"]
    assert calculated_column_count(inventory) == expected["calculated"]
    assert counts.get("measure", 0) == expected["measure"]
    assert counts.get("relationship", 0) == expected["relationship"]
    assert counts.get("role", 0) == expected["role"]


@pytest.mark.parametrize("model_path", FIXTURE_MODELS, ids=project_name)
def test_every_object_type_matches_raw_json_counts(model_path):
    document = load_model_document(model_path)

    counts = inventory_for(model_path).count_by_type()

    for object_type, raw_count in raw_object_counts(document).items():
        assert counts.get(object_type, 0) == raw_count, object_type


@pytest.mark.parametrize("model_path", FIXTURE_MODELS, ids=project_name)
def test_m_partition_shapes_match_design_document(model_path):
    inventory = inventory_for(model_path)
    shapes = {}
    for partition in inventory.items_of_type("partition"):
        shape = partition.facts.get("m_shape")
        if shape is not None:
            shapes[shape] = shapes.get(shape, 0) + 1

    assert shapes == M_SHAPE_COUNTS[project_name(model_path)]


def test_empty_calculated_column_is_reported_in_historical_model():
    model_path = next(path for path in FIXTURE_MODELS if project_name(path).startswith("HISTORICAL"))

    findings = inventory_for(model_path).findings()

    assert ("column:EPAY/Add Column2", "calculated column has no expression") in findings


@pytest.mark.parametrize("model_path", FIXTURE_MODELS, ids=project_name)
def test_local_now_partitions_are_reported(model_path):
    findings = inventory_for(model_path).findings()
    local_now = [identity for identity, text in findings if "DateTime.LocalNow" in text]

    if project_name(model_path).startswith("HISTORICAL"):
        assert local_now == []
    else:
        assert local_now
        assert all(identity.startswith("partition:DIM_DATE/") for identity in local_now)


@pytest.mark.parametrize("model_path", FIXTURE_MODELS, ids=project_name)
def test_credentials_are_not_inventoried(model_path):
    inventory = inventory_for(model_path)
    source_dump = json.dumps(
        [{"properties": item.properties, "facts": item.facts} for item in inventory.items_of_type("data_source")]
    )

    assert '"Username"' not in source_dump
    assert "oracle_user" not in source_dump
    assert all(item.facts.get("authentication_kind") == "UsernamePassword"
               for item in inventory.items_of_type("data_source"))


def test_role_members_are_counted_not_copied():
    document = minimal_document(
        roles=[{"name": "Readers", "modelPermission": "read", "members": [{"memberName": "person@example.com"}]}],
    )

    role = build_inventory(document).items["role:Readers"]

    assert role.facts == {"member_count": 1}
    assert "members" not in role.properties
    assert "person@example.com" not in json.dumps(role.properties)


def test_expression_hash_is_the_same_for_string_and_list_forms():
    string_form = minimal_document(
        tables=[{"name": "T", "measures": [{"name": "Total", "expression": "SUM(T[x])"}]}],
    )
    list_form = minimal_document(
        tables=[{"name": "T", "measures": [{"name": "Total", "expression": ["SUM(T[x])"]}]}],
    )

    string_item = build_inventory(string_form).items["measure:T/Total"]
    list_item = build_inventory(list_form).items["measure:T/Total"]

    assert string_item.expression_sha256 == list_item.expression_sha256
    assert (string_item.expression_form, list_item.expression_form) == ("string", "list")


def test_expression_hash_changes_when_expression_changes():
    before = minimal_document(tables=[{"name": "T", "measures": [{"name": "Total", "expression": "SUM(T[x])"}]}])
    after = minimal_document(tables=[{"name": "T", "measures": [{"name": "Total", "expression": "SUM(T[y])"}]}])

    assert (build_inventory(before).items["measure:T/Total"].expression_sha256
            != build_inventory(after).items["measure:T/Total"].expression_sha256)


def test_expression_text_is_not_stored_in_the_inventory():
    document = minimal_document(tables=[{"name": "T", "measures": [{"name": "Total", "expression": "SUM(T[secret])"}]}])

    item = build_inventory(document).items["measure:T/Total"]

    assert "secret" not in json.dumps(item.properties)
    assert "expression" not in item.properties


def test_duplicate_table_names_are_rejected():
    document = minimal_document(tables=[{"name": "T"}, {"name": "T"}])

    with pytest.raises(InventoryError, match="duplicate object identity: table:T"):
        build_inventory(document)


def test_object_without_name_is_rejected():
    document = minimal_document(tables=[{"columns": []}])

    with pytest.raises(InventoryError, match="table without a name"):
        build_inventory(document)
