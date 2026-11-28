"""Step 8 model specification: the JSON file the user writes to describe a new model.

Parsing refuses anything outside the approved format. It checks for credentials first, then the
structure, then the references between tables, columns, relationships and measures. The first
structural problem is reported with its path, for example "tables[1].columns[0].data_type".

A spec never holds credentials. A key that looks like one is refused, and its value is never shown.
The server is a placeholder that is set in Visual Studio later.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ssas_agent.policy import Operation, PathPolicy
from ssas_agent.validation.measure_form import measure_form_reasons
from ssas_agent.validation.model_index import name_key

SPEC_VERSION = 1
SUPPORTED_COMPATIBILITY_LEVEL = 1500
SUPPORTED_SOURCE_KIND = "oracle"
DEFAULT_CULTURE = "en-US"
PROJECT_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
CREDENTIAL_KEY_FRAGMENTS = ("password", "secret", "token", "username", "userid", "credential")

TOP_LEVEL_KEYS = frozenset(
    {"spec_version", "project_name", "compatibility_level", "culture", "data_source",
     "tables", "relationships", "measures"}
)
DATA_SOURCE_KEYS = frozenset({"name", "kind", "server"})
TABLE_KEYS = frozenset({"name", "grain", "power_query", "columns"})
COLUMN_KEYS = frozenset({"name", "data_type", "source_column", "is_key"})
RELATIONSHIP_KEYS = frozenset({"from_table", "from_column", "to_table", "to_column"})
MEASURE_KEYS = frozenset({"table", "name", "expression", "kpi"})


class DataType(StrEnum):
    STRING = "string"
    INT64 = "int64"
    DECIMAL = "decimal"
    DOUBLE = "double"
    BOOLEAN = "boolean"
    DATETIME = "dateTime"


class SpecError(ValueError):
    """The spec is refused. The message names the first problem found, with its path."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = tuple(problems)
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class DataSourceSpec:
    name: str
    server: str


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    data_type: DataType
    source_column: str
    is_key: bool


@dataclass(frozen=True)
class TableSpec:
    name: str
    grain: str
    power_query: str | None
    columns: tuple[ColumnSpec, ...]


@dataclass(frozen=True)
class RelationshipSpec:
    from_table: str
    from_column: str
    to_table: str
    to_column: str


@dataclass(frozen=True)
class MeasureSpec:
    table: str
    name: str
    expression: str
    kpi: str


@dataclass(frozen=True)
class ModelSpec:
    project_name: str
    compatibility_level: int
    culture: str
    data_source: DataSourceSpec
    tables: tuple[TableSpec, ...]
    relationships: tuple[RelationshipSpec, ...]
    measures: tuple[MeasureSpec, ...]


def read_spec_file(policy: PathPolicy, spec_path: Path) -> str:
    """Read a spec through the path policy. Only folders the policy allows for reading (for example specs/) work."""
    readable_path = policy.enforce(Operation.READ, spec_path)
    try:
        return readable_path.read_bytes().decode("utf-8-sig")
    except OSError:
        raise SpecError([f"spec file cannot be read: {spec_path.name}"]) from None
    except UnicodeDecodeError:
        raise SpecError([f"spec file is not UTF-8 text: {spec_path.name}"]) from None


def parse_spec_text(text: str) -> ModelSpec:
    """Parse and check a spec. Raises SpecError with the first problem found."""
    raw = _load_object(text)
    credential_problems = _credential_problems(raw, "spec")
    if credential_problems:
        raise SpecError(credential_problems)
    _refuse_unknown_keys(raw, TOP_LEVEL_KEYS, "spec")
    _check_header(raw)
    tables = _build_tables(raw.get("tables"))
    tables_by_key = {name_key(table.name): table for table in tables}
    relationships = _build_relationships(raw.get("relationships", []), tables_by_key)
    measures = _build_measures(raw.get("measures", []), tables_by_key)
    return ModelSpec(
        project_name=raw["project_name"],
        compatibility_level=SUPPORTED_COMPATIBILITY_LEVEL,
        culture=_require_text(raw.get("culture", DEFAULT_CULTURE), "culture"),
        data_source=_data_source(raw.get("data_source"), "data_source"),
        tables=tables,
        relationships=relationships,
        measures=measures,
    )


def _load_object(text: str) -> dict[str, Any]:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as error:
        raise SpecError([f"spec is not valid JSON (line {error.lineno}, column {error.colno})"]) from None
    if not isinstance(raw, dict):
        raise SpecError(["spec must be one JSON object"])
    return raw


def _credential_problems(node: Any, path: str) -> list[str]:
    """Find keys that look like credentials. Only the key name is reported, never the value."""
    problems: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}"
            if any(fragment in key.lower() for fragment in CREDENTIAL_KEY_FRAGMENTS):
                problems.append(
                    f"{child_path} looks like a credential; set credentials in Visual Studio, not in the spec"
                )
            problems.extend(_credential_problems(value, child_path))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            problems.extend(_credential_problems(item, f"{path}[{index}]"))
    return problems


def _refuse_unknown_keys(body: dict[str, Any], allowed: frozenset[str], path: str) -> None:
    unknown = sorted(set(body) - allowed)
    if unknown:
        raise SpecError([f"{path} has unknown key(s): {', '.join(unknown)}"])


def _check_header(raw: dict[str, Any]) -> None:
    if raw.get("spec_version") != SPEC_VERSION:
        raise SpecError([f"spec_version must be {SPEC_VERSION}"])
    if raw.get("compatibility_level") != SUPPORTED_COMPATIBILITY_LEVEL:
        raise SpecError([f"compatibility_level must be {SUPPORTED_COMPATIBILITY_LEVEL} (SSAS 2019)"])
    project_name = raw.get("project_name")
    if not isinstance(project_name, str) or not PROJECT_NAME_PATTERN.fullmatch(project_name):
        raise SpecError(["project_name must start with a letter and use only letters, digits and '_' (max 64)"])


def _data_source(raw: Any, path: str) -> DataSourceSpec:
    body = _require_object(raw, path)
    _refuse_unknown_keys(body, DATA_SOURCE_KEYS, path)
    if body.get("kind") != SUPPORTED_SOURCE_KIND:
        raise SpecError([f"{path}.kind must be '{SUPPORTED_SOURCE_KIND}' (the only source in phase 1)"])
    return DataSourceSpec(
        name=_require_text(body.get("name"), f"{path}.name"),
        server=_require_text(body.get("server"), f"{path}.server"),
    )


def _build_tables(raw: Any) -> tuple[TableSpec, ...]:
    items = _require_list(raw, "tables")
    if not items:
        raise SpecError(["tables must list at least one table"])
    tables = tuple(_table(item, f"tables[{index}]") for index, item in enumerate(items))
    _refuse_duplicate_names([table.name for table in tables], "table")
    return tables


def _table(raw: Any, path: str) -> TableSpec:
    body = _require_object(raw, path)
    _refuse_unknown_keys(body, TABLE_KEYS, path)
    columns = tuple(
        _column(item, f"{path}.columns[{index}]")
        for index, item in enumerate(_require_list(body.get("columns"), f"{path}.columns"))
    )
    if not columns:
        raise SpecError([f"{path}.columns must list at least one column"])
    _refuse_duplicate_names([column.name for column in columns], f"column in {path}")
    return TableSpec(
        name=_require_text(body.get("name"), f"{path}.name"),
        grain=_require_text(body.get("grain"), f"{path}.grain"),
        power_query=_optional_power_query(body.get("power_query"), f"{path}.power_query"),
        columns=columns,
    )


def _column(raw: Any, path: str) -> ColumnSpec:
    body = _require_object(raw, path)
    _refuse_unknown_keys(body, COLUMN_KEYS, path)
    name = _require_text(body.get("name"), f"{path}.name")
    return ColumnSpec(
        name=name,
        data_type=_data_type(body.get("data_type"), f"{path}.data_type"),
        source_column=_require_text(body.get("source_column", name), f"{path}.source_column"),
        is_key=_require_bool(body.get("is_key", False), f"{path}.is_key"),
    )


def _data_type(raw: Any, path: str) -> DataType:
    try:
        return DataType(raw)
    except ValueError:
        allowed = ", ".join(member.value for member in DataType)
        raise SpecError([f"{path} must be one of: {allowed}"]) from None


def _build_relationships(raw: Any, tables_by_key: dict[str, TableSpec]) -> tuple[RelationshipSpec, ...]:
    relationships = []
    for index, item in enumerate(_require_list(raw, "relationships")):
        path = f"relationships[{index}]"
        body = _require_object(item, path)
        _refuse_unknown_keys(body, RELATIONSHIP_KEYS, path)
        relationship = RelationshipSpec(
            from_table=_require_text(body.get("from_table"), f"{path}.from_table"),
            from_column=_require_text(body.get("from_column"), f"{path}.from_column"),
            to_table=_require_text(body.get("to_table"), f"{path}.to_table"),
            to_column=_require_text(body.get("to_column"), f"{path}.to_column"),
        )
        _require_column(tables_by_key, relationship.from_table, relationship.from_column, path)
        _require_column(tables_by_key, relationship.to_table, relationship.to_column, path)
        relationships.append(relationship)
    return tuple(relationships)


def _build_measures(raw: Any, tables_by_key: dict[str, TableSpec]) -> tuple[MeasureSpec, ...]:
    measures = tuple(
        _measure(item, f"measures[{index}]", tables_by_key)
        for index, item in enumerate(_require_list(raw, "measures"))
    )
    _refuse_duplicate_measures(measures)
    return measures


def _measure(raw: Any, path: str, tables_by_key: dict[str, TableSpec]) -> MeasureSpec:
    body = _require_object(raw, path)
    _refuse_unknown_keys(body, MEASURE_KEYS, path)
    measure = MeasureSpec(
        table=_require_text(body.get("table"), f"{path}.table"),
        name=_require_text(body.get("name"), f"{path}.name"),
        expression=_require_text(body.get("expression"), f"{path}.expression"),
        kpi=_require_text(body.get("kpi"), f"{path}.kpi"),
    )
    if name_key(measure.table) not in tables_by_key:
        raise SpecError([f"{path}: table '{measure.table}' is not in the spec"])
    reasons = measure_form_reasons(measure.name, measure.expression)
    if reasons:
        raise SpecError([f"{path}: {reasons[0]}"])
    return measure


def _refuse_duplicate_measures(measures: tuple[MeasureSpec, ...]) -> None:
    seen: set[tuple[str, str]] = set()
    for measure in measures:
        key = (name_key(measure.table), name_key(measure.name))
        if key in seen:
            raise SpecError([f"measure '{measure.table}[{measure.name}]' is used more than once (names ignore case)"])
        seen.add(key)


def _require_column(tables_by_key: dict[str, TableSpec], table_name: str, column_name: str, path: str) -> None:
    table = tables_by_key.get(name_key(table_name))
    if table is None:
        raise SpecError([f"{path}: table '{table_name}' is not in the spec"])
    column_keys = {name_key(column.name) for column in table.columns}
    if name_key(column_name) not in column_keys:
        raise SpecError([f"{path}: column '{table_name}[{column_name}]' is not in the spec"])


def _refuse_duplicate_names(names: list[str], label: str) -> None:
    seen: set[str] = set()
    for name in names:
        key = name_key(name)
        if key in seen:
            raise SpecError([f"{label} name '{name}' is used more than once (names ignore case)"])
        seen.add(key)


def _require_object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpecError([f"{path} must be an object"])
    return value


def _require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SpecError([f"{path} must be a list"])
    return value


def _require_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError([f"{path} must be non-empty text"])
    return value.strip()


def _require_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise SpecError([f"{path} must be true or false"])
    return value


def _optional_power_query(value: Any, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise SpecError([f"{path} must be text or null"])
    return value.replace("\r\n", "\n")
