"""Deny-by-default path policy. Every read and write the agent performs is checked here.

Relative paths are resolved against the project root, not the current directory.
Paths are resolved (".." and symlinks followed) before any folder check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

PROTECTED_FOLDERS = ("example_models", "tests/fixtures")
READABLE_FOLDERS = ("example_models", "tests/fixtures", "workspaces", "artifacts")
WRITABLE_FOLDERS = ("workspaces", "artifacts")


class Operation(Enum):
    READ = "read"
    WRITE = "write"


class PolicyDeniedError(PermissionError):
    """Raised when the path policy does not allow an operation."""


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    resolved_path: Path


@dataclass(frozen=True)
class PathPolicy:
    project_root: Path

    def decide(self, operation: Any, requested_path: Path | str) -> PolicyDecision:
        resolved = (self._root / Path(requested_path)).resolve()
        if not isinstance(operation, Operation):
            return self._deny(f"unknown operation: {operation!r}", resolved)
        if operation is Operation.WRITE:
            return self._decide_write(resolved)
        return self._decide_read(resolved)

    def enforce(self, operation: Any, requested_path: Path | str) -> Path:
        """Return the resolved path if allowed, otherwise raise PolicyDeniedError."""
        decision = self.decide(operation, requested_path)
        if not decision.allowed:
            raise PolicyDeniedError(decision.reason)
        return decision.resolved_path

    @property
    def _root(self) -> Path:
        return Path(self.project_root).resolve()

    def _decide_write(self, resolved: Path) -> PolicyDecision:
        protected = self._matching_folder(resolved, PROTECTED_FOLDERS)
        if protected is not None:
            return self._deny(f"'{protected}' is protected from writes", resolved)
        folder = self._matching_folder(resolved, WRITABLE_FOLDERS)
        if folder is None:
            return self._deny("write is outside the allowed folders", resolved)
        return PolicyDecision(True, f"write allowed in '{folder}'", resolved)

    def _decide_read(self, resolved: Path) -> PolicyDecision:
        folder = self._matching_folder(resolved, READABLE_FOLDERS)
        if folder is None:
            return self._deny("read is outside the allowed folders", resolved)
        return PolicyDecision(True, f"read allowed in '{folder}'", resolved)

    def _matching_folder(self, resolved: Path, folder_names: tuple[str, ...]) -> str | None:
        for folder_name in folder_names:
            if resolved.is_relative_to(self._root / folder_name):
                return folder_name
        return None

    @staticmethod
    def _deny(reason: str, resolved: Path) -> PolicyDecision:
        return PolicyDecision(False, reason, resolved)
