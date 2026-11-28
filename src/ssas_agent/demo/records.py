"""What the exit-gate demonstration records. Each outcome holds plain values, so the report can be written from them."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NewModelOutcome:
    run_id: str
    project_name: str
    model_path: str
    project_path: str
    mapping_path: str
    model_sha256: str
    errors: int
    warnings: int
    not_checked: tuple[str, ...]


@dataclass(frozen=True)
class EditOutcome:
    run_id: str
    source_path: str
    target_path: str
    candidate_sha256: str
    change_summary: dict[str, Any]
    category_summary: dict[str, Any]
    staged_by: str
    approved_by: str
    outcome: str
    state: str
    verified: bool
    verification: dict[str, Any]


@dataclass(frozen=True)
class RefusalRecord:
    case: str
    refused: bool
    reason: str


@dataclass(frozen=True)
class ExitGateResult:
    run_prefix: str
    new_model: NewModelOutcome | None
    edit: EditOutcome | None
    refusals: tuple[RefusalRecord, ...]
    refusals_wrote_nothing: bool
    stopped_reason: str | None

    @property
    def passed(self) -> bool:
        return (
            self.stopped_reason is None
            and self.new_model is not None
            and self.edit is not None
            and self.edit.verified
            and self.refusals_wrote_nothing
            and all(refusal.refused for refusal in self.refusals)
        )
