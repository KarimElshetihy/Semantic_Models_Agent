"""What staging returns: everything needed to review the proposal and, after approval, to apply it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ssas_agent.approval.proposal import ProposalBinding


class StagingError(RuntimeError):
    """Raised when a change cannot be staged: the workspace already exists or the candidate fails its own check."""


@dataclass(frozen=True)
class StagedChange:
    run_id: str
    proposal: ProposalBinding
    workspace_model: Path
    candidate_path: Path
    review_folder: Path
    change_summary: dict[str, int]
    category_summary: dict[str, int]
