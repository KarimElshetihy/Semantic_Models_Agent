"""Records describing what changed between two model inventories."""

from __future__ import annotations

from dataclasses import dataclass

ADDED = "added"
REMOVED = "removed"
CHANGED = "changed"
CHANGE_KINDS = (ADDED, REMOVED, CHANGED)


@dataclass(frozen=True)
class ObjectChange:
    """One object that was added, removed or changed. Names only, never values."""

    identity: str
    object_type: str
    change_kind: str
    changed_properties: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticDiff:
    changes: tuple[ObjectChange, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.changes

    def of_kind(self, change_kind: str) -> tuple[ObjectChange, ...]:
        return tuple(change for change in self.changes if change.change_kind == change_kind)

    def summary(self) -> dict[str, int]:
        return {change_kind: len(self.of_kind(change_kind)) for change_kind in CHANGE_KINDS}
