"""Pluggable similarity for dedupe / future semantic backends (local deterministic default)."""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable


def normalize_for_similarity(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t[:50_000]


def jaccard_tokens(a: str, b: str) -> float:
    ta = set(re.findall(r"\w{3,}", normalize_for_similarity(a)))
    tb = set(re.findall(r"\w{3,}", normalize_for_similarity(b)))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / max(1, union)


@runtime_checkable
class SimilarityBackend(Protocol):
    async def similarity(self, a: str, b: str) -> float:
        """Return score in ``[0, 1]`` (1 = identical)."""
        ...


class LexicalJaccardSimilarity:
    """Default async-compatible lexical similarity (no embeddings)."""

    async def similarity(self, a: str, b: str) -> float:
        return float(jaccard_tokens(a, b))


def default_similarity_backend() -> SimilarityBackend:
    return LexicalJaccardSimilarity()
