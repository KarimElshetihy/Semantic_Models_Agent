"""Run artifacts under artifacts/{run_id}/.

Every write passes the path policy, uses an atomic replace, and is redacted.
Event lines are appended to events.jsonl in time order.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ssas_agent.audit.redaction import redact_text
from ssas_agent.audit.run_ids import validate_run_id
from ssas_agent.bim.storage import write_bytes_atomically
from ssas_agent.clock import utc_now_iso
from ssas_agent.policy import Operation, PathPolicy

EVENTS_FILE_NAME = "events.jsonl"
JSON_INDENT = 2


class RunRecorder:
    def __init__(self, policy: PathPolicy, artifacts_root: Path, run_id: str) -> None:
        validated_run_id = validate_run_id(run_id)
        self._run_dir = policy.enforce(Operation.WRITE, Path(artifacts_root) / validated_run_id)
        self._run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def run_dir(self) -> Path:
        return self._run_dir

    def write_json(self, file_name: str, payload: Any) -> Path:
        text = json.dumps(payload, indent=JSON_INDENT, sort_keys=True, ensure_ascii=False)
        return self.write_text(file_name, text + "\n")

    def write_text(self, file_name: str, text: str) -> Path:
        target = self._artifact_path(file_name)
        write_bytes_atomically(target, redact_text(text).encode("utf-8"))
        return target

    def append_event(self, event_type: str, details: dict[str, Any]) -> None:
        record = {"timestamp": utc_now_iso(), "event": event_type, **details}
        line = redact_text(json.dumps(record, sort_keys=True, ensure_ascii=False))
        with self._artifact_path(EVENTS_FILE_NAME).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")

    def _artifact_path(self, file_name: str) -> Path:
        if not file_name or Path(file_name).name != file_name or file_name in (".", ".."):
            raise ValueError(f"artifact name must be a plain file name: {file_name!r}")
        return self._run_dir / file_name
