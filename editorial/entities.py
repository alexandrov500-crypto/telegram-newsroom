"""Rule-based entity extraction (regex + normalization)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

EntityKind = Literal["person", "organization", "country", "product", "crypto", "technology", "other"]


@dataclass(slots=True)
class EntitySpan:
    kind: EntityKind
    text: str
    normalized: str


_COUNTRY = re.compile(
    r"\b(USA|U\.S\.A\.|US|UK|EU|Russia|China|India|Germany|France|Spain|Italy|Sweden|Finland|Norway|Ukraine)\b",
    re.I,
)
_CRYPTO = re.compile(r"\b(Bitcoin|BTC|Ethereum|ETH|Solana|SOL|USDT|USDC|XRP|Dogecoin)\b", re.I)
_TECH = re.compile(r"\b(AI|GPT|OpenAI|Kubernetes|Docker|Python|Linux|AWS|Azure|GPU|LLM)\b", re.I)
_ORG = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s+(?:Inc|LLC|Ltd|Corp|Company))\b")
# crude person: two capitalized tokens (lots of false positives — heuristic only)
_PERSON = re.compile(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b")


def normalize_entity(s: str) -> str:
    return " ".join(s.lower().split())[:120]


def extract_entities(text: str, *, max_entities: int = 32) -> list[EntitySpan]:
    t = text or ""
    out: list[EntitySpan] = []

    def add(kind: EntityKind, m: str) -> None:
        if len(out) >= max_entities:
            return
        norm = normalize_entity(m)
        if not norm or any(e.normalized == norm for e in out):
            return
        out.append(EntitySpan(kind=kind, text=m.strip()[:200], normalized=norm))

    for m in _COUNTRY.findall(t):
        add("country", m)
    for m in _CRYPTO.findall(t):
        add("crypto", m)
    for m in _TECH.findall(t):
        add("technology", m)
    for m in _ORG.findall(t):
        add("organization", m)
    for m in _PERSON.findall(t):
        add("person", m)
    return out


def record_entity_cooccurrence(
    runtime_dir: str | None,
    entities: list[EntitySpan],
    *,
    max_pairs: int = 200,
) -> None:
    from editorial.intelligence_store import entity_stats_path, load_json, save_json

    path = entity_stats_path(runtime_dir)
    data = load_json(path, {"version": 1, "entities": {}, "pairs": {}})
    ent = dict(data.get("entities") or {})
    pairs = dict(data.get("pairs") or {})
    for e in entities:
        ent[e.normalized] = int(ent.get(e.normalized) or 0) + 1
    norms = [e.normalized for e in entities]
    for i, a in enumerate(norms):
        for b in norms[i + 1 :]:
            if a == b:
                continue
            k = "|".join(sorted((a, b)))
            pairs[k] = int(pairs.get(k) or 0) + 1
    # trim pairs
    if len(pairs) > max_pairs:
        pairs = dict(sorted(pairs.items(), key=lambda kv: -kv[1])[:max_pairs])
    data["entities"] = ent
    data["pairs"] = pairs
    save_json(path, data)
