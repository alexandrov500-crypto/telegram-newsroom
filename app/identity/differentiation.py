"""Anti-generic content differentiation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_GENERIC_OPENERS = re.compile(
    r"^(важная\s+новость|сообщается|по\s+данным|according\s+to|"
    r"информационное\s+агентство|источники\s+сообщают)",
    re.I,
)

_RECENT_PATH = "differentiation_recent.json"


@dataclass(frozen=True)
class DifferentiationVerdict:
    unique: bool
    redundancy_score: float
    reason: str


def _token_shingle(text: str, n: int = 4) -> set[str]:
    words = re.findall(r"[a-zа-яё0-9]{3,}", (text or "").lower())
    return {" ".join(words[i : i + n]) for i in range(max(0, len(words) - n + 1))}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def evaluate_differentiation(text: str, *, runtime_dir: str) -> DifferentiationVerdict:
    t = (text or "").strip()
    if _GENERIC_OPENERS.search(t):
        return DifferentiationVerdict(False, 0.85, "generic_opener")

    shingles = _token_shingle(t)
    p = Path(runtime_dir) / _RECENT_PATH
    try:
        recent: list[dict[str, Any]] = json.loads(p.read_text(encoding="utf-8")).get("posts", [])
    except (OSError, json.JSONDecodeError):
        recent = []

    max_sim = 0.0
    for row in recent[:30]:
        prev = set(row.get("shingles") or [])
        max_sim = max(max_sim, _jaccard(shingles, prev))

    if max_sim >= 0.62:
        return DifferentiationVerdict(False, round(max_sim, 4), "near_duplicate_structure")
    if max_sim >= 0.45:
        return DifferentiationVerdict(True, round(max_sim, 4), "moderate_overlap")
    return DifferentiationVerdict(True, round(max_sim, 4), "unique")


def record_published_structure(text: str, *, runtime_dir: str) -> None:
    p = Path(runtime_dir) / _RECENT_PATH
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"posts": []}
    posts = list(data.get("posts") or [])
    posts.insert(
        0,
        {
            "hash": hashlib.sha256((text or "")[:400].encode()).hexdigest()[:16],
            "shingles": sorted(_token_shingle(text))[:40],
        },
    )
    data["posts"] = posts[:35]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
