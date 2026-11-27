"""Builds the knowledge index. Every file is checked against the path policy, read, and hashed.

Files that are unsupported, too large, not UTF-8, or outside the policy are listed as skipped, with a reason.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ssas_agent.knowledge.records import (
    KnowledgeDocument,
    KnowledgeFileType,
    KnowledgeIndex,
    SkippedFile,
    SkipReason,
)
from ssas_agent.policy import Operation, PathPolicy, PolicyDeniedError

KNOWLEDGE_FOLDER = "knowledge"
MAX_FILE_BYTES = 200_000
SUPPORTED_SUFFIXES = frozenset(file_type.value for file_type in KnowledgeFileType)


def build_index(
    policy: PathPolicy,
    folder_name: str = KNOWLEDGE_FOLDER,
    max_file_bytes: int = MAX_FILE_BYTES,
) -> KnowledgeIndex:
    folder = _readable_folder(policy, folder_name)
    if folder is None:
        return KnowledgeIndex(documents=(), skipped=())
    documents: list[KnowledgeDocument] = []
    skipped: list[SkippedFile] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        relative_path = f"{folder_name}/{path.relative_to(folder).as_posix()}"
        outcome = _load_file(policy, relative_path, path, max_file_bytes)
        if isinstance(outcome, KnowledgeDocument):
            documents.append(outcome)
        else:
            skipped.append(outcome)
    return KnowledgeIndex(documents=tuple(documents), skipped=tuple(skipped))


def _readable_folder(policy: PathPolicy, folder_name: str) -> Path | None:
    try:
        folder = policy.enforce(Operation.READ, folder_name)
    except PolicyDeniedError:
        return None
    return folder if folder.is_dir() else None


def _load_file(
    policy: PathPolicy,
    relative_path: str,
    path: Path,
    max_file_bytes: int,
) -> KnowledgeDocument | SkippedFile:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        return SkippedFile(relative_path, SkipReason.UNSUPPORTED_TYPE)
    if not policy.decide(Operation.READ, relative_path).allowed:
        return SkippedFile(relative_path, SkipReason.OUTSIDE_POLICY)
    if path.stat().st_size > max_file_bytes:
        return SkippedFile(relative_path, SkipReason.TOO_LARGE)
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return SkippedFile(relative_path, SkipReason.NOT_UTF8)
    return KnowledgeDocument(relative_path, hashlib.sha256(raw).hexdigest(), text)
