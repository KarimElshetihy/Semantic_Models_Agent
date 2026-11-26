"""Build a read-only inventory of a Model.bim document, keyed by object identity.

Identities (see docs/PHASE0_DESIGN.md section 6):
    table:{table}, column:{table}/{column}, measure:{table}/{measure},
    partition:{table}/{partition}, relationship:{name}, role:{role},
    role-permission:{role}/{table}, datasource:{name}

Connection credentials and role member lists are never copied into the inventory.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from ssas_agent.bim.document import sha256_hex
from ssas_agent.bim.expressions import expression_form, expression_text, m_partition_shape
from ssas_agent.inventory.findings import column_findings, partition_findings
from ssas_agent.inventory.records import InventoryError, InventoryItem, ModelInventory

TABLE_CHILD_KEYS = ("columns", "measures", "partitions")
ROLE_CHILD_KEYS = ("tablePermissions", "members")
PERMISSION_EXPRESSION_KEY = "filterExpression"
CREDENTIAL_KEY = "credential"
AUTHENTICATION_KIND_KEY = "AuthenticationKind"


def build_inventory(document: dict[str, Any]) -> ModelInventory:
    model = document["model"]
    collector = _InventoryCollector()
    for table in model.get("tables", []):
        _collect_table(collector, table)
    for relationship in model.get("relationships", []):
        _collect_relationship(collector, relationship)
    for role in model.get("roles", []):
        _collect_role(collector, role)
    for source in model.get("dataSources", []):
        _collect_data_source(collector, source)
    return collector.build()


class _InventoryCollector:
    def __init__(self) -> None:
        self._items: dict[str, InventoryItem] = {}

    def add(self, item: InventoryItem) -> None:
        if item.identity in self._items:
            raise InventoryError(f"duplicate object identity: {item.identity}")
        self._items[item.identity] = item

    def build(self) -> ModelInventory:
        return ModelInventory(items=dict(self._items))


def _collect_table(collector: _InventoryCollector, table: dict[str, Any]) -> None:
    table_name = _required_name(table, "table")
    collector.add(make_item(f"table:{table_name}", "table", table, excluded_keys=TABLE_CHILD_KEYS))
    for column in table.get("columns", []):
        _collect_column(collector, table_name, column)
    for measure in table.get("measures", []):
        _collect_measure(collector, table_name, measure)
    for partition in table.get("partitions", []):
        _collect_partition(collector, table_name, partition)


def _collect_column(collector: _InventoryCollector, table_name: str, column: dict[str, Any]) -> None:
    identity = f"column:{table_name}/{_required_name(column, 'column')}"
    item = make_item(identity, "column", column, excluded_keys=("expression",), findings=column_findings(column))
    collector.add(with_expression(item, column.get("expression")))


def _collect_measure(collector: _InventoryCollector, table_name: str, measure: dict[str, Any]) -> None:
    identity = f"measure:{table_name}/{_required_name(measure, 'measure')}"
    collector.add(_expression_item(identity, "measure", measure, "expression"))


def _collect_partition(collector: _InventoryCollector, table_name: str, partition: dict[str, Any]) -> None:
    identity = f"partition:{table_name}/{_required_name(partition, 'partition')}"
    source = partition.get("source", {})
    facts = {"source_type": source.get("type")}
    if source.get("type") == "m":
        facts["m_shape"] = m_partition_shape(expression_text(source.get("expression")))
    item = make_item(
        identity,
        "partition",
        partition,
        excluded_keys=("source",),
        facts=facts,
        findings=partition_findings(partition),
    )
    collector.add(with_expression(item, source.get("expression")))


def _collect_relationship(collector: _InventoryCollector, relationship: dict[str, Any]) -> None:
    identity = f"relationship:{_required_name(relationship, 'relationship')}"
    collector.add(make_item(identity, "relationship", relationship))


def _collect_role(collector: _InventoryCollector, role: dict[str, Any]) -> None:
    role_name = _required_name(role, "role")
    member_count = len(role.get("members") or [])
    collector.add(
        make_item(
            f"role:{role_name}",
            "role",
            role,
            excluded_keys=ROLE_CHILD_KEYS,
            facts={"member_count": member_count},
        )
    )
    for permission in role.get("tablePermissions", []):
        permission_name = _required_name(permission, "table permission")
        identity = f"role-permission:{role_name}/{permission_name}"
        collector.add(_expression_item(identity, "role_permission", permission, PERMISSION_EXPRESSION_KEY))


def _collect_data_source(collector: _InventoryCollector, source: dict[str, Any]) -> None:
    source_name = _required_name(source, "data source")
    credential = source.get(CREDENTIAL_KEY) or {}
    collector.add(
        make_item(
            f"datasource:{source_name}",
            "data_source",
            source,
            excluded_keys=(CREDENTIAL_KEY,),
            facts={"authentication_kind": credential.get(AUTHENTICATION_KIND_KEY)},
        )
    )


def make_item(
    identity: str,
    object_type: str,
    raw_object: dict[str, Any],
    excluded_keys: tuple[str, ...] = (),
    facts: dict[str, Any] | None = None,
    findings: list[str] | tuple[str, ...] = (),
) -> InventoryItem:
    skipped_keys = set(excluded_keys)
    properties = {key: value for key, value in raw_object.items() if key not in skipped_keys}
    return InventoryItem(
        identity=identity,
        object_type=object_type,
        properties=properties,
        facts=dict(facts or {}),
        findings=tuple(findings),
    )


def with_expression(item: InventoryItem, expression: Any) -> InventoryItem:
    """Attach a hash and storage form for an expression. Objects without expressions are unchanged."""
    if expression is None:
        return item
    digest = sha256_hex(expression_text(expression).encode("utf-8"))
    return replace(item, expression_sha256=digest, expression_form=expression_form(expression))


def _expression_item(
    identity: str,
    object_type: str,
    raw_object: dict[str, Any],
    expression_key: str,
) -> InventoryItem:
    item = make_item(identity, object_type, raw_object, excluded_keys=(expression_key,))
    return with_expression(item, raw_object.get(expression_key))


def _required_name(raw_object: dict[str, Any], kind: str) -> str:
    name = raw_object.get("name")
    if not isinstance(name, str) or not name:
        raise InventoryError(f"{kind} without a name")
    return name
