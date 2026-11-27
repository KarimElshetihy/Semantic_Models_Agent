"""Knowledge retrieval with provenance: index the approved knowledge folder, find matches, and build reference blocks."""

from ssas_agent.knowledge.index import KNOWLEDGE_FOLDER, MAX_FILE_BYTES, build_index
from ssas_agent.knowledge.prompt import MAX_CONTEXT_CHARACTERS, reference_block
from ssas_agent.knowledge.records import (
    KnowledgeDocument,
    KnowledgeFileType,
    KnowledgeIndex,
    KnowledgeMatch,
    SkippedFile,
    SkipReason,
)
from ssas_agent.knowledge.retrieve import DEFAULT_LIMIT, retrieve

__all__ = [
    "DEFAULT_LIMIT",
    "KNOWLEDGE_FOLDER",
    "MAX_CONTEXT_CHARACTERS",
    "MAX_FILE_BYTES",
    "KnowledgeDocument",
    "KnowledgeFileType",
    "KnowledgeIndex",
    "KnowledgeMatch",
    "SkipReason",
    "SkippedFile",
    "build_index",
    "reference_block",
    "retrieve",
]
