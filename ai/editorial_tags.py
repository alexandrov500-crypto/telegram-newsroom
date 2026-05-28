from __future__ import annotations

import json
import re
from typing import Any

_CATEGORIES = (
    "AI",
    "Politics",
    "Crypto",
    "Security",
    "Markets",
    "Startups",
    "Breaking",
    "Technology",
    "World",
    "Business",
)

_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AI": (r"\bai\b", r"gpt", r"openai", r"llm", r"neural", r"модел", r"интеллект"),
    "Politics": (r"\belection\b", r"parliament", r"minister", r"политик", r"выбор"),
    "Crypto": (r"\bbitcoin\b", r"\bbtc\b", r"ethereum", r"blockchain", r"крипт"),
    "Security": (r"\bhack\b", r"malware", r"vulnerability", r"cve", r"безопасност", r"утечк"),
    "Markets": (r"\bstock\b", r"nasdaq", r"fed rate", r"inflation", r"рынок", r"акци"),
    "Startups": (r"startup", r"funding", r"seed round", r"unicorn", r"стартап"),
    "Breaking": (r"breaking", r"urgent", r"just in", r"срочно", r"шок"),
    "Technology": (r"\btech\b", r"software", r"chip", r"semiconductor", r"технолог"),
    "World": (r"\bun\b", r"nato", r"war in", r"мира", r"конфликт"),
    "Business": (r"\bearnings\b", r"revenue", r"ceo", r"merger", r"бизнес", r"компани"),
}


def _text_blob(content: str, sources: Any) -> str:
    parts = [content or ""]
    if isinstance(sources, list):
        parts.append(" ".join(str(x.get("channel", "")) for x in sources if isinstance(x, dict)))
    elif isinstance(sources, str):
        try:
            data = json.loads(sources)
            if isinstance(data, list):
                parts.append(" ".join(str(x.get("channel", "")) for x in data if isinstance(x, dict)))
        except (json.JSONDecodeError, TypeError):
            parts.append(sources[:500])
    blob = " ".join(parts).lower()
    return blob


def infer_editorial_tags(content: str, sources: Any) -> dict[str, Any]:
    """
    Heuristic category + tags + confidence. Deterministic ordering by category name tie-break.
    """
    blob = _text_blob(content, sources)
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {c: [] for c in _CATEGORIES}
    for cat, patterns in _KEYWORDS.items():
        s = 0.0
        for pat in patterns:
            if re.search(pat, blob, re.IGNORECASE):
                s += 0.18
                matched[cat].append(pat)
        if s > 0:
            scores[cat] = min(0.95, s)
    if not scores:
        best = "Technology"
        conf = 0.35
        reason = "No strong keyword match; default Technology bucket."
    else:
        best = max(scores.items(), key=lambda kv: (kv[1], -_CATEGORIES.index(kv[0]) if kv[0] in _CATEGORIES else 0))[0]
        conf = round(float(scores[best]), 3)
        hits = matched.get(best) or []
        reason = (
            f"Ключевые слова ({len(hits)}): " + ", ".join(sorted(set(hits))[:6])
            if hits
            else "Оценка по пересечению тем."
        )
    tags: list[str] = []
    for t in sorted(set(re.findall(r"#[\w\u0400-\u04FF]{2,32}", content or "", flags=re.UNICODE))):
        tags.append(t)
    if best and f"#{best.lower()}" not in [x.lower() for x in tags]:
        tags.append(f"#{best}")
    tags = sorted(set(tags))[:12]
    return {
        "category": best,
        "category_confidence": conf,
        "category_reasoning": reason[:500],
        "inferred_tags": tags,
        "category_scores": {k: round(v, 3) for k, v in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:8]},
    }
