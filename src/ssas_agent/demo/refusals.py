"""The refusal half of the exit gate: unsafe requests are tried and must be refused, with nothing written.

Each case is run inside one snapshot of the folders the policy protects or writes to. If any file was added,
removed or changed by the refusals, the gate fails.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ssas_agent.demo.records import RefusalRecord
from ssas_agent.demo.steps import EXISTING_MODEL_PATH, STAGING_ACTOR, edit_measure
from ssas_agent.newmodel import SpecError, parse_spec_text
from ssas_agent.policy import PathPolicy, PolicyDeniedError
from ssas_agent.staging import ChangeStager, StagingError

SNAPSHOT_FOLDERS = ("example_models", "tests/fixtures", "output", "workspaces", "artifacts", "specs")
PROTECTED_FIXTURE_TARGET = Path("tests") / "fixtures" / "RETA_MODEL" / "Model.bim"
BAD_MEASURE_NAME = "Bad[Name]"
REFUSAL_ERRORS = (SpecError, PolicyDeniedError, StagingError)
REFUSED_REFUSAL_OUTCOME = "the request was NOT refused"
SECOND_FILE_NAME = "Other.bim"

FileSnapshot = frozenset[tuple[str, int, int]]


def run_refusals(
    policy: PathPolicy,
    stager: ChangeStager,
    spec_text: str,
    run_prefix: str,
    destination: Path,
) -> tuple[tuple[RefusalRecord, ...], bool]:
    """Run every refusal case. Returns the records and whether the snapshot folders were left untouched."""
    before = snapshot_folders(policy.project_root)
    records = (
        _refused("spec with a bracket in a measure name", lambda: _parse_bad_spec(spec_text)),
        _refused(
            "write into the protected fixtures folder",
            lambda: _stage_to(stager, run_prefix, "refused-fixtures", PROTECTED_FIXTURE_TARGET),
        ),
        _refused(
            "write to a second file in the destination folder",
            lambda: _stage_to(stager, run_prefix, "refused-second-file", destination.parent / SECOND_FILE_NAME),
        ),
    )
    after = snapshot_folders(policy.project_root)
    return records, before == after


def snapshot_folders(project_root: Path) -> FileSnapshot:
    """Path, size and modification time of every file in the snapshot folders."""
    entries = set()
    for folder in SNAPSHOT_FOLDERS:
        for path in (project_root / folder).rglob("*"):
            if path.is_file():
                stat = path.stat()
                entries.add((path.relative_to(project_root).as_posix(), stat.st_size, stat.st_mtime_ns))
    return frozenset(entries)


def _refused(case: str, attempt: Callable[[], object]) -> RefusalRecord:
    try:
        attempt()
    except REFUSAL_ERRORS as error:
        return RefusalRecord(case=case, refused=True, reason=str(error))
    return RefusalRecord(case=case, refused=False, reason=REFUSED_REFUSAL_OUTCOME)


def _parse_bad_spec(spec_text: str) -> None:
    raw = json.loads(spec_text)
    raw["measures"][0]["name"] = BAD_MEASURE_NAME
    parse_spec_text(json.dumps(raw))


def _stage_to(stager: ChangeStager, run_prefix: str, suffix: str, target: Path) -> None:
    stager.stage(
        f"{run_prefix}-{suffix}",
        STAGING_ACTOR,
        EXISTING_MODEL_PATH,
        edit_measure,
        "refused request",
        target_model=target,
    )
