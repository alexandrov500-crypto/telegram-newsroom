from __future__ import annotations

import re
from collections.abc import Sequence

WEAK_PHRASES: tuple[str, ...] = (
    "continues to",
    "gradually",
    "experts say",
    "according to reports",
    "amid concerns",
    "amid growing",
    "in a move that",
    "it remains to be seen",
    "sources say",
    "reportedly",
    "landscape",
    "underscores",
    "navigate",
    "delve",
    "robust",
    "leverage",
    "spearhead",
)

AI_GENERIC_OPENERS: tuple[str, ...] = (
    "in today's",
    "as the world",
    "in a significant",
    "marking a",
    "highlighting the",
    "shedding light",
    "comes amid",
    "amid heightened",
)

FILLER_TOKENS: frozenset[str] = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "that",
        "this",
        "it",
        "its",
        "their",
        "has",
        "have",
        "had",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "also",
        "said",
        "says",
    },
)

_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


def find_weak_phrases(text: str) -> list[str]:
    lower = (text or "").lower()
    return [p for p in WEAK_PHRASES if p in lower]


def find_generic_openers(text: str) -> list[str]:
    lower = (text or "").lower()[:120]
    return [p for p in AI_GENERIC_OPENERS if p in lower]


def opening_trigram(text: str) -> str:
    words = tokenize(text)[:3]
    return " ".join(words)


def phrase_hits_in_corpus(phrase: str, corpus: Sequence[str]) -> int:
    needle = phrase.lower()
    return sum(1 for block in corpus if needle in (block or "").lower())


def jaccard_similarity(a: str, b: str) -> float:
    sa, sb = set(tokenize(a)), set(tokenize(b))
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0
