"""Semantic dedup — collapse redundant story nodes before compression."""

from __future__ import annotations

import re
from typing import Any

_TOPIC_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("macro_control", re.compile(r"(цб|центральн.*банк|контрол.*налич|банк.*контрол|регулятор.*банк)", re.I)),
    ("sanctions", re.compile(r"(санкци|sanction|embargo)", re.I)),
    ("rates", re.compile(r"(ключев.*ставк|rate\s+hike|rate\s+cut|повыш.*ставк)", re.I)),
    ("crypto_enforcement", re.compile(r"(уголов|крипт|crypto.*crime|бирж.*закрыт)", re.I)),
    ("eu_social", re.compile(r"(eu\b|ес\b|соцсет|social\s+media.*eu)", re.I)),
    ("ukraine", re.compile(r"(украин|ukraine|мерц|zelensky)", re.I)),
]


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", (text or "").lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def macro_topic_key(text: str) -> str | None:
    for key, rx in _TOPIC_PATTERNS:
        if rx.search(text or ""):
            return key
    return None


def collapse_topic_duplicates(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep strongest item per macro topic key (e.g. two CB control stories → one)."""
    by_topic: dict[str, dict[str, Any]] = {}
    rest: list[dict[str, Any]] = []
    for it in items:
        key = macro_topic_key(str(it.get("text") or ""))
        score = float(it.get("final_score") or 0.0)
        if not key:
            rest.append(it)
            continue
        prev = by_topic.get(key)
        if prev is None or score > float(prev.get("final_score") or 0.0):
            by_topic[key] = it
    return list(by_topic.values()) + rest


def dedupe_within_cluster(
    items: list[dict[str, Any]],
    *,
    similarity_threshold: float = 0.6,
) -> list[dict[str, Any]]:
    """Drop near-duplicate items inside a cluster; keep highest final_score."""
    kept: list[dict[str, Any]] = []
    token_cache: list[set[str]] = []
    for it in sorted(items, key=lambda x: float(x.get("final_score") or 0.0), reverse=True):
        tokens = _tokenize(str(it.get("text") or ""))
        if len(tokens) < 5:
            kept.append(it)
            token_cache.append(tokens)
            continue
        dup = False
        for prev_tok in token_cache:
            if _jaccard(tokens, prev_tok) >= similarity_threshold:
                dup = True
                break
        if not dup:
            kept.append(it)
            token_cache.append(tokens)
    return kept
