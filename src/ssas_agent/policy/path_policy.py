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
READABLE_FOLDERS = ("example_models", "tests/fixtures", "workspaces", "artifacts", "knowledge", "specs")
WRITABLE_FOLDERS = ("workspaces", "artifacts")
# Exact files at the project root that may be read (never written). Only the local settings file.
READABLE_FILES = (".env",)
# The one file that may be read and written inside the optional named destination folder (step 9).
APPLY_TARGET_FILE = "Model.bim"
DEFAULT_APPLY_FOLDER = "output"


class Operation(Enum):
    READ = "read"
    WRITE = "write"


class PolicyDeniedError(PermissionError):
    """Raised when the path policy does not allow an operation."""


class PolicyConfigurationError(ValueError):
    """Raised when the policy is configured with an unsafe destination folder."""


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    resolved_path: Path


@dataclass(frozen=True)
class PathPolicy:
    """`apply_folder` names the one destination for approved changes. Only `Model.bim` in it is opened up."""

    project_root: Path
    apply_folder: Path | None = None

    def __post_init__(self) -> None:
        if self.apply_folder is not None:
            self._refuse_unsafe_apply_folder(self._resolved_apply_folder())

    @property
    def apply_target(self) -> Path | None:
        """The only file inside the destination folder that may be read or written, if a folder is named."""
        if self.apply_folder is None:
            return None
        return self._resolved_apply_folder() / APPLY_TARGET_FILE

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
        if self._is_apply_target(resolved):
            return PolicyDecision(True, "write allowed for the named destination model", resolved)
        protected = self._matching_folder(resolved, PROTECTED_FOLDERS)
        if protected is not None:
            return self._deny(f"'{protected}' is protected from writes", resolved)
        folder = self._matching_folder(resolved, WRITABLE_FOLDERS)
        if folder is None:
            return self._deny("write is outside the allowed folders", resolved)
        return PolicyDecision(True, f"write allowed in '{folder}'", resolved)

    def _decide_read(self, resolved: Path) -> PolicyDecision:
        if self._is_readable_file(resolved):
            return PolicyDecision(True, "read allowed for a project settings file", resolved)
        if self._is_apply_target(resolved):
            return PolicyDecision(True, "read allowed for the named destination model", resolved)
        folder = self._matching_folder(resolved, READABLE_FOLDERS)
        if folder is None:
            return self._deny("read is outside the allowed folders", resolved)
        return PolicyDecision(True, f"read allowed in '{folder}'", resolved)

    def _is_readable_file(self, resolved: Path) -> bool:
        return any(resolved == self._root / file_name for file_name in READABLE_FILES)

    def _is_apply_target(self, resolved: Path) -> bool:
        return self.apply_target is not None and resolved == self.apply_target

    def _resolved_apply_folder(self) -> Path:
        return (self._root / Path(self.apply_folder)).resolve()

    def _refuse_unsafe_apply_folder(self, folder: Path) -> None:
        """The destination must not be, contain, or overlap the project root or any folder the policy already names."""
        if folder == self._root or self._root.is_relative_to(folder):
            raise PolicyConfigurationError("the destination folder must not be or contain the project root")
        if folder.is_file():
            raise PolicyConfigurationError(f"the destination folder is a file: {folder}")
        for reserved_name in sorted(set(READABLE_FOLDERS) | set(WRITABLE_FOLDERS)):
            reserved = self._root / reserved_name
            if folder.is_relative_to(reserved) or reserved.is_relative_to(folder):
                raise PolicyConfigurationError(
                    f"the destination folder must not overlap the policy folder '{reserved_name}'"
                )

    def _matching_folder(self, resolved: Path, folder_names: tuple[str, ...]) -> str | None:
        for folder_name in folder_names:
            if resolved.is_relative_to(self._root / folder_name):
                return folder_name
        return None

    @staticmethod
    def _deny(reason: str, resolved: Path) -> PolicyDecision:
        return PolicyDecision(False, reason, resolved)
