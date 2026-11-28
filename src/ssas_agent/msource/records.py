"""Records for the offline M source reader (step 8a). Every reference and column keeps the M line it came from."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ReadingStatus(StrEnum):
    UNDERSTOOD = "understood"
    PARTIAL = "partial"
    NOT_UNDERSTOOD = "not_understood"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class SourceReference:
    reference: str
    schema: str | None
    name: str
    line: int


@dataclass(frozen=True)
class SourceColumn:
    name: str
    line: int
    alias: str | None = None


@dataclass(frozen=True)
class SqlReading:
    references: tuple[SourceReference, ...]
    select_all: bool
    columns: tuple[SourceColumn, ...]
    problems: tuple[str, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SourceReading:
    table: str
    status: ReadingStatus
    data_source: str | None
    sql: SqlReading | None
    notes: tuple[str, ...]
