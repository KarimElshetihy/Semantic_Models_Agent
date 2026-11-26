"""Inventory records: one entry per model object, keyed by a stable identity string."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


class InventoryError(ValueError):
    """Raised when a model cannot be inventoried safely, for example duplicate identities or unnamed objects."""


@dataclass
class InventoryItem:
    """Read-only facts about one model object. Expression text is never stored, only its hash."""

    identity: str
    object_type: str
    properties: dict[str, Any] = field(default_factory=dict)
    expression_sha256: str | None = None
    expression_form: str | None = None
    facts: dict[str, Any] = field(default_factory=dict)
    findings: tuple[str, ...] = ()


@dataclass
class ModelInventory:
    items: dict[str, InventoryItem]

    def count_by_type(self) -> dict[str, int]:
        return dict(Counter(item.object_type for item in self.items.values()))

    def items_of_type(self, object_type: str) -> list[InventoryItem]:
        return [item for item in self.items.values() if item.object_type == object_type]

    def findings(self) -> list[tuple[str, str]]:
        """Return (identity, finding text) pairs for every finding in the model."""
        return [(item.identity, text) for item in self.items.values() for text in item.findings]
