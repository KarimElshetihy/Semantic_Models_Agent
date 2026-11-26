"""Run identifiers. A run ID becomes a folder name, so it must never contain path characters."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
RANDOM_SUFFIX_LENGTH = 8


class InvalidRunIdError(ValueError):
    """Raised when a run ID is not a safe single folder name."""


def new_run_id(now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    suffix = uuid.uuid4().hex[:RANDOM_SUFFIX_LENGTH]
    return f"{moment.strftime(TIMESTAMP_FORMAT)}-{suffix}"


def validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not RUN_ID_PATTERN.fullmatch(run_id):
        raise InvalidRunIdError(f"invalid run id: {run_id!r}")
    return run_id
