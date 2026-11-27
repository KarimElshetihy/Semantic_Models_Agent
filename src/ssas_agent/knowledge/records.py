"""Records for the knowledge index. Every document carries its source path and content hash (provenance)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class KnowledgeFileType(StrEnum):
    MARKDOWN = ".md"
    TEXT = ".txt"


class SkipReason(StrEnum):
    UNSUPPORTED_TYPE = "unsupported file type"
    OUTSIDE_POLICY = "outside the read policy"
    TOO_LARGE = "larger than the size limit"
    NOT_UTF8 = "not UTF-8 text"


@dataclass(frozen=True)
class KnowledgeDocument:
    relative_path: str
    sha256: str
    text: str


@dataclass(frozen=True)
class SkippedFile:
    relative_path: str
    reason: SkipReason


@dataclass(frozen=True)
class KnowledgeIndex:
    documents: tuple[KnowledgeDocument, ...]
    skipped: tuple[SkippedFile, ...]


@dataclass(frozen=True)
class KnowledgeMatch:
    relative_path: str
    sha256: str
    score: int
    excerpt: str
    document_text: str
