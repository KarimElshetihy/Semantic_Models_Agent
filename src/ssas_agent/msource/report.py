"""Writes the source report to artifacts/{run_id}/sources.json.

The report holds references, columns, line numbers and notes. It never holds the M text or the SQL text.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from ssas_agent.audit.recorder import RunRecorder
from ssas_agent.msource.reader import read_model_sources, status_counts
from ssas_agent.msource.records import SourceReading
from ssas_agent.policy import PathPolicy

SOURCES_FILE_NAME = "sources.json"


class SourceEvent(StrEnum):
    SOURCES_READ = "sources_read"


def record_source_report(
    policy: PathPolicy,
    artifacts_root: Path,
    run_id: str,
    data: dict[str, Any],
) -> Path:
    readings = read_model_sources(data)
    recorder = RunRecorder(policy, artifacts_root, run_id)
    path = recorder.write_json(SOURCES_FILE_NAME, sources_payload(readings))
    recorder.append_event(SourceEvent.SOURCES_READ, {"partitions": len(readings), "counts": status_counts(readings)})
    return path


def sources_payload(readings: tuple[SourceReading, ...]) -> dict[str, Any]:
    return {
        "counts": status_counts(readings),
        "tables": [_reading_payload(reading) for reading in readings],
    }


def _reading_payload(reading: SourceReading) -> dict[str, Any]:
    sql = reading.sql
    return {
        "table": reading.table,
        "status": reading.status.value,
        "data_source": reading.data_source,
        "references": [
            {"reference": item.reference, "schema": item.schema, "name": item.name, "line": item.line}
            for item in (sql.references if sql else ())
        ],
        "select_all": sql.select_all if sql else False,
        "columns": [{"name": column.name, "line": column.line} for column in (sql.columns if sql else ())],
        "notes": list(reading.notes),
    }
