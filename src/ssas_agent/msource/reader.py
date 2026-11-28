"""Reads the source of each Power Query partition in a model. Offline: no database is contacted.

Status per partition:
- understood: the native query was read and nothing was left out.
- partial: it was read, but something was left out (an expression column, a comma-joined table, later steps).
- not understood: the shape is not recognised, or the SQL text has a problem. Nothing is guessed.
- not applicable: the partition is not Power Query (for example a calculated table).
"""

from __future__ import annotations

from typing import Any

from ssas_agent.bim.expressions import expression_text
from ssas_agent.msource.native_query import find_native_query
from ssas_agent.msource.records import ReadingStatus, SourceReading, SqlReading
from ssas_agent.msource.sql_reading import read_sql

GENERATED_VALUES_MARKER = "#date("
UNRECOGNISED_SHAPE_NOTE = (
    "Power Query shape not recognised; only let Source = Value.NativeQuery(...) in Source is read"
)
GENERATED_VALUES_NOTE = "generated values (#date), not read from a source"


def read_model_sources(data: dict[str, Any]) -> tuple[SourceReading, ...]:
    readings = [
        read_partition(table["name"], partition)
        for table in data["model"].get("tables", [])
        for partition in table.get("partitions", [])
    ]
    return tuple(readings)


def read_partition(table_name: str, partition: dict[str, Any]) -> SourceReading:
    source = partition.get("source", {})
    if source.get("type") != "m":
        note = f"not a Power Query partition (type: {source.get('type')})"
        return SourceReading(table_name, ReadingStatus.NOT_APPLICABLE, None, None, (note,))
    m_text = expression_text(source.get("expression"))
    query = find_native_query(m_text)
    if query is None:
        return SourceReading(table_name, ReadingStatus.NOT_UNDERSTOOD, None, None, (_shape_note(m_text),))
    sql = read_sql(query.sql, first_line=query.sql_start_line)
    notes = (*query.notes, *sql.problems, *sql.notes)
    return SourceReading(table_name, _status(sql, query.notes), query.data_source, sql, notes)


def status_counts(readings: tuple[SourceReading, ...]) -> dict[str, int]:
    counts = {status.value: 0 for status in ReadingStatus}
    for reading in readings:
        counts[reading.status.value] += 1
    return counts


def _status(sql: SqlReading, query_notes: tuple[str, ...]) -> ReadingStatus:
    if sql.problems:
        return ReadingStatus.NOT_UNDERSTOOD
    if query_notes or sql.notes:
        return ReadingStatus.PARTIAL
    return ReadingStatus.UNDERSTOOD


def _shape_note(m_text: str) -> str:
    return GENERATED_VALUES_NOTE if GENERATED_VALUES_MARKER in m_text else UNRECOGNISED_SHAPE_NOTE
