"""The requirements template: the eight fields that section 4 of requirements.md asks for.

Every value records where it came from: entered by the user, drafted by the model, or missing.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum


class RequirementsError(ValueError):
    """The request cannot be used, for example because it is empty."""


class RequirementField(StrEnum):
    BUSINESS_OBJECTIVES = "business_objectives"
    KPIS = "kpis"
    DATA_SOURCES = "data_sources"
    TABLE_GRAIN = "table_grain"
    KEYS = "keys"
    REFRESH = "refresh"
    SECURITY = "security"
    TARGET_SSAS_VERSION = "target_ssas_version"


FIELD_LABELS: Mapping[RequirementField, str] = {
    RequirementField.BUSINESS_OBJECTIVES: "Business objectives",
    RequirementField.KPIS: "Required KPIs",
    RequirementField.DATA_SOURCES: "Data sources",
    RequirementField.TABLE_GRAIN: "Table grain",
    RequirementField.KEYS: "Keys",
    RequirementField.REFRESH: "Refresh requirements",
    RequirementField.SECURITY: "Security requirements",
    RequirementField.TARGET_SSAS_VERSION: "Target SSAS version",
}


class FieldSource(StrEnum):
    USER = "entered by user"
    DRAFTED_BY_MODEL = "drafted by model"
    MISSING = "missing"


@dataclass(frozen=True)
class FieldValue:
    text: str
    source: FieldSource


@dataclass(frozen=True)
class RequirementSpec:
    request_text: str
    values: Mapping[RequirementField, FieldValue]
    dropped_drafts: tuple[RequirementField, ...] = ()
    draft_note: str = ""

    def missing_fields(self) -> tuple[RequirementField, ...]:
        return tuple(field for field in RequirementField if self.values[field].source is FieldSource.MISSING)


def blank_spec(request_text: str) -> RequirementSpec:
    values = {field: FieldValue("", FieldSource.MISSING) for field in RequirementField}
    return RequirementSpec(request_text=request_text, values=values)
