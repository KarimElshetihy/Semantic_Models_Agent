"""Writes a new model candidate to workspaces/{run_id}/{project}/ and its mapping to artifacts/{run_id}/.

Nothing is written unless the built model passes the static checks with no errors. An existing output
folder is never overwritten. The mapping lists tables, columns, relationships and measures, with the KPI
each measure answers. It never holds Power Query text or the server name.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from ssas_agent.audit.recorder import RunRecorder
from ssas_agent.audit.run_ids import validate_run_id
from ssas_agent.bim.document import serialize_visual_studio_bytes
from ssas_agent.bim.storage import write_bytes_atomically
from ssas_agent.newmodel.build import build_model_document, relationship_name
from ssas_agent.newmodel.errors import NewModelRefusedError
from ssas_agent.newmodel.project_file import MODEL_FILE_NAME, PROJECT_EXTENSION, project_file_text
from ssas_agent.newmodel.spec import ModelSpec, TableSpec
from ssas_agent.policy import Operation, PathPolicy
from ssas_agent.validation import run_static_checks
from ssas_agent.validation.findings import ERROR

WORKSPACES_FOLDER = "workspaces"
DEFAULT_ARTIFACTS_PATH = Path("artifacts")
MAPPING_FILE_NAME = "mapping.json"
NOT_CHECKED_NOTE = "Power Query partitions are copied as written and not checked (not checked in phase 1)."
CREDENTIAL_NOTE = "The data source has no credential. Set it in Visual Studio before processing."


class NewModelEvent(StrEnum):
    MODEL_WRITTEN = "new_model_written"


@dataclass(frozen=True)
class NewModelCandidate:
    project_dir: Path
    model_path: Path
    project_path: Path
    mapping_path: Path


def create_new_model(
    policy: PathPolicy,
    spec: ModelSpec,
    run_id: str,
    artifacts_root: Path = DEFAULT_ARTIFACTS_PATH,
    project_guid: str | None = None,
) -> NewModelCandidate:
    """Build the model, check it, and write the candidate. Raises NewModelRefusedError before writing anything if it fails."""
    validate_run_id(run_id)
    document = build_model_document(spec)
    _refuse_if_checks_fail(document)
    project_dir = policy.enforce(Operation.WRITE, Path(WORKSPACES_FOLDER) / run_id / spec.project_name)
    if project_dir.exists():
        raise NewModelRefusedError((f"output folder already exists for this run: {project_dir}",))
    guid = project_guid or str(uuid.uuid4()).upper()
    model_path, project_path = _write_project_files(policy, project_dir, spec, document, guid)
    recorder = RunRecorder(policy, artifacts_root, run_id)
    mapping_path = recorder.write_json(MAPPING_FILE_NAME, mapping_payload(spec))
    recorder.append_event(NewModelEvent.MODEL_WRITTEN, _event_details(spec))
    return NewModelCandidate(project_dir, model_path, project_path, mapping_path)


def mapping_payload(spec: ModelSpec) -> dict[str, Any]:
    """The reviewable source mapping (AC-01). It holds no Power Query text and no server name."""
    return {
        "project_name": spec.project_name,
        "data_source": spec.data_source.name,
        "tables": [_table_mapping(table) for table in spec.tables],
        "relationships": [
            {
                "name": relationship_name(relationship),
                "from": f"{relationship.from_table}[{relationship.from_column}]",
                "to": f"{relationship.to_table}[{relationship.to_column}]",
            }
            for relationship in spec.relationships
        ],
        "measures": [{"table": measure.table, "name": measure.name, "kpi": measure.kpi} for measure in spec.measures],
        "notes": [NOT_CHECKED_NOTE, CREDENTIAL_NOTE],
    }


def _table_mapping(table: TableSpec) -> dict[str, Any]:
    return {
        "name": table.name,
        "grain": table.grain,
        "columns": [column.name for column in table.columns],
        "partition": "present" if table.power_query is not None else "none",
    }


def _refuse_if_checks_fail(document: dict[str, Any]) -> None:
    report = run_static_checks(document)
    reasons = [
        f"{finding.rule_id} at {finding.identity}: {finding.evidence}"
        for finding in report.findings
        if finding.severity == ERROR
    ]
    if reasons:
        raise NewModelRefusedError(tuple(reasons))


def _write_project_files(
    policy: PathPolicy,
    project_dir: Path,
    spec: ModelSpec,
    document: dict[str, Any],
    project_guid: str,
) -> tuple[Path, Path]:
    project_dir.mkdir(parents=True, exist_ok=False)
    model_path = policy.enforce(Operation.WRITE, project_dir / MODEL_FILE_NAME)
    project_path = policy.enforce(Operation.WRITE, project_dir / f"{spec.project_name}{PROJECT_EXTENSION}")
    write_bytes_atomically(model_path, serialize_visual_studio_bytes(document))
    write_bytes_atomically(project_path, project_file_text(spec.project_name, project_guid).encode("utf-8"))
    return model_path, project_path


def _event_details(spec: ModelSpec) -> dict[str, Any]:
    return {
        "project": spec.project_name,
        "tables": len(spec.tables),
        "relationships": len(spec.relationships),
        "measures": len(spec.measures),
    }
