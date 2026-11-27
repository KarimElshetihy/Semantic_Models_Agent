"""Keyword retrieval over the knowledge index. Deterministic: the same index and query always give the same order.

Score = number of distinct query terms that appear in a document. Ties are broken by path.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from ssas_agent.knowledge.records import KnowledgeDocument, KnowledgeIndex, KnowledgeMatch

DEFAULT_LIMIT = 3
EXCERPT_CHARACTERS = 240
STOP_WORDS = frozenset({"a", "an", "and", "are", "for", "in", "is", "of", "on", "or", "the", "to", "with"})
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.casefold())


def query_terms(query: str) -> frozenset[str]:
    return frozenset(token for token in tokenize(query) if token not in STOP_WORDS)


def retrieve(index: KnowledgeIndex, query: str, limit: int = DEFAULT_LIMIT) -> list[KnowledgeMatch]:
    terms = query_terms(query)
    if not terms:
        return []
    matches = [match for document in index.documents if (match := _score(document, terms)) is not None]
    matches.sort(key=lambda match: (-match.score, match.relative_path))
    return matches[:limit]


def _score(document: KnowledgeDocument, terms: frozenset[str]) -> KnowledgeMatch | None:
    counts = Counter(tokenize(document.text))
    found = {term for term in terms if counts[term]}
    if not found:
        return None
    return KnowledgeMatch(
        relative_path=document.relative_path,
        sha256=document.sha256,
        score=len(found),
        excerpt=_excerpt(document.text, found),
        document_text=document.text,
    )


def _excerpt(text: str, terms: Iterable[str]) -> str:
    wanted = set(terms)
    for line in text.splitlines():
        if wanted & set(tokenize(line)):
            return line.strip()[:EXCERPT_CHARACTERS]
    return text.strip()[:EXCERPT_CHARACTERS]
