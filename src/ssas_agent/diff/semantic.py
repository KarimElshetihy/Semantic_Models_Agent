"""Compare two model inventories by object identity.

Rules (see docs/PHASE0_DESIGN.md section 7):
- An identity present on one side only is added or removed.
- A changed object lists the names of the properties, facts and expression that differ.
- Expression text is compared by hash, so a change of storage form alone
  (string versus list of lines) is reported as a note, not as an expression change.
- Renames are not detected. A renamed object appears as removed plus added.
"""

from __future__ import annotations

from typing import Any

from ssas_agent.diff.records import ADDED, CHANGED, REMOVED, ObjectChange, SemanticDiff
from ssas_agent.inventory import InventoryItem, ModelInventory

EXPRESSION_CHANGED = "expression"
FACTS_PREFIX = "facts."
FORM_CHANGED_NOTE = "expression form changed"
_MISSING = object()


def diff_inventories(before: ModelInventory, after: ModelInventory) -> SemanticDiff:
    changes = []
    for identity in sorted(before.items.keys() | after.items.keys()):
        change = _compare_item(identity, before.items.get(identity), after.items.get(identity))
        if change is not None:
            changes.append(change)
    return SemanticDiff(changes=tuple(changes))


def _compare_item(
    identity: str,
    before_item: InventoryItem | None,
    after_item: InventoryItem | None,
) -> ObjectChange | None:
    if before_item is None:
        return ObjectChange(identity, after_item.object_type, ADDED)
    if after_item is None:
        return ObjectChange(identity, before_item.object_type, REMOVED)
    changed_names = _changed_names(before_item, after_item)
    notes = _notes(before_item, after_item)
    if not changed_names and not notes:
        return None
    return ObjectChange(identity, after_item.object_type, CHANGED, tuple(sorted(changed_names)), tuple(notes))


def _changed_names(before_item: InventoryItem, after_item: InventoryItem) -> set[str]:
    names = _differing_keys(before_item.properties, after_item.properties)
    names |= {FACTS_PREFIX + key for key in _differing_keys(before_item.facts, after_item.facts)}
    if before_item.expression_sha256 != after_item.expression_sha256:
        names.add(EXPRESSION_CHANGED)
    return names


def _notes(before_item: InventoryItem, after_item: InventoryItem) -> list[str]:
    notes = []
    if _expression_form_changed(before_item, after_item):
        notes.append(FORM_CHANGED_NOTE)
    return notes


def _expression_form_changed(before_item: InventoryItem, after_item: InventoryItem) -> bool:
    both_have_form = before_item.expression_form is not None and after_item.expression_form is not None
    return both_have_form and before_item.expression_form != after_item.expression_form


def _differing_keys(before_mapping: dict[str, Any], after_mapping: dict[str, Any]) -> set[str]:
    keys = before_mapping.keys() | after_mapping.keys()
    return {
        key
        for key in keys
        if before_mapping.get(key, _MISSING) != after_mapping.get(key, _MISSING)
    }
