"""Classify each semantic change as breaking, review, additive or cosmetic (spec ENG-06).

Rules (docs/PHASE1_DESIGN.md section 3):
- An object removed is breaking. A rename shows as a removal plus an addition, so it is breaking too.
- A changed data type or relationship endpoint is breaking.
- An added object is additive.
- A changed expression, a changed fact, or any other property is review: a person must check it.
- Presentation properties (description, display folder, format, annotations) and storage-form notes are cosmetic.

When one change touches several properties, the most serious category wins.
"""

from __future__ import annotations

from dataclasses import dataclass

from ssas_agent.diff.records import ADDED, REMOVED, ObjectChange, SemanticDiff

BREAKING = "breaking"
REVIEW = "review"
ADDITIVE = "additive"
COSMETIC = "cosmetic"
CATEGORIES = (BREAKING, REVIEW, ADDITIVE, COSMETIC)  # most serious first

BREAKING_PROPERTIES = frozenset({"dataType", "fromTable", "fromColumn", "toTable", "toColumn"})
COSMETIC_PROPERTIES = frozenset({"description", "displayFolder", "formatString", "annotations"})

Verdict = tuple[str, str]  # (category, reason)


@dataclass(frozen=True)
class ClassifiedChange:
    change: ObjectChange
    category: str
    reasons: tuple[str, ...]


def classify_changes(diff: SemanticDiff) -> tuple[ClassifiedChange, ...]:
    return tuple(_classify(change) for change in sorted(diff.changes, key=lambda change: change.identity))


def _classify(change: ObjectChange) -> ClassifiedChange:
    if change.change_kind == REMOVED:
        return ClassifiedChange(change, BREAKING, ("object removed",))
    if change.change_kind == ADDED:
        return ClassifiedChange(change, ADDITIVE, ("object added",))
    verdicts = [_property_verdict(name) for name in change.changed_properties]
    verdicts.extend(_note_verdict(note) for note in change.notes)
    if not verdicts:
        return ClassifiedChange(change, REVIEW, ("change could not be classified",))
    category = min(verdicts, key=lambda verdict: CATEGORIES.index(verdict[0]))[0]
    return ClassifiedChange(change, category, tuple(reason for _, reason in verdicts))


def _property_verdict(property_name: str) -> Verdict:
    reason = f"{property_name} changed"
    if property_name in BREAKING_PROPERTIES:
        return BREAKING, reason
    if property_name in COSMETIC_PROPERTIES:
        return COSMETIC, reason
    return REVIEW, reason


def _note_verdict(note: str) -> Verdict:
    return COSMETIC, note


def category_counts(classified: tuple[ClassifiedChange, ...]) -> dict[str, int]:
    return {category: sum(1 for item in classified if item.category == category) for category in CATEGORIES}
