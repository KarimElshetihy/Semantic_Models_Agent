"""Compare two versions of a Model.bim: the semantic object diff, a category for each change,
and the raw text diff. Names and categories only in the structured payload, never expression text."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ssas_agent.bim.document import BimDocument
from ssas_agent.diff.classify import BREAKING, ClassifiedChange, category_counts, classify_changes
from ssas_agent.diff.records import ObjectChange, SemanticDiff
from ssas_agent.diff.semantic import diff_inventories
from ssas_agent.diff.text import unified_text_diff
from ssas_agent.inventory import build_inventory


@dataclass(frozen=True)
class VersionComparison:
    semantic: SemanticDiff
    classified: tuple[ClassifiedChange, ...]
    text_diff: str

    @property
    def has_breaking_changes(self) -> bool:
        return self.category_summary()[BREAKING] > 0

    def category_summary(self) -> dict[str, int]:
        return category_counts(self.classified)

    def to_payload(self) -> dict[str, Any]:
        return {
            "summary": self.semantic.summary(),
            "categories": self.category_summary(),
            "changes": [_change_payload(item) for item in self.classified],
        }


def compare_documents(before: BimDocument, after: BimDocument, label: str) -> VersionComparison:
    """`before` is the file as loaded; `after` is an edited document, serialized the way it would be saved."""
    semantic = diff_inventories(build_inventory(before.data), build_inventory(after.data))
    text_diff = unified_text_diff(before.source_bytes, after.to_bytes(), label)
    return VersionComparison(semantic=semantic, classified=classify_changes(semantic), text_diff=text_diff)


def _change_payload(item: ClassifiedChange) -> dict[str, Any]:
    change: ObjectChange = item.change
    return {
        "identity": change.identity,
        "object_type": change.object_type,
        "change_kind": change.change_kind,
        "category": item.category,
        "reasons": list(item.reasons),
        "changed_properties": list(change.changed_properties),
        "notes": list(change.notes),
    }
