"""Approval bindings: the exact facts an approval is tied to (design section 8 and spec section 5).

An approval binds to the run, the proposal, the base and candidate file hashes,
the target path and a hash of the operation summary. Any change to these facts
makes the approval stale.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ssas_agent.bim.document import sha256_hex


@dataclass(frozen=True)
class ProposalBinding:
    run_id: str
    proposal_id: str
    base_sha256: str | None
    candidate_sha256: str
    target_path: str
    operation_sha256: str

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> ProposalBinding:
        return cls(**payload)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of_value(value: Any) -> str:
    return sha256_hex(canonical_json(value).encode("utf-8"))


def file_sha256(path: Path) -> str | None:
    """SHA-256 of the file, or None when the file does not exist."""
    if not path.exists():
        return None
    return sha256_hex(path.read_bytes())
