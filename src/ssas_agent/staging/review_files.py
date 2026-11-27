"""Review files written under artifacts/{run_id}/: the classified diff, the text diff and the run facts.

All writes go through RunRecorder, so they pass the path policy and are redacted.
"""

from __future__ import annotations

from typing import Any

from ssas_agent.audit.recorder import RunRecorder
from ssas_agent.diff import VersionComparison

DIFF_JSON_FILE = "diff.json"
DIFF_TEXT_FILE = "diff.txt"
RUN_FILE = "run.json"


def write_review_files(
    recorder: RunRecorder,
    comparison: VersionComparison,
    run_facts: dict[str, Any],
) -> None:
    recorder.write_json(DIFF_JSON_FILE, comparison.to_payload())
    recorder.write_text(DIFF_TEXT_FILE, comparison.text_diff)
    recorder.write_json(RUN_FILE, run_facts)
