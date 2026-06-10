"""Content segment taxonomy for segment-aware growth intelligence."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Any


class ContentSegment(str, Enum):
    POLITICS = "politics"
    MARKETS = "markets"
    ECONOMY = "economy"
    TECHNOLOGY = "technology"
    SCIENCE = "science"
    WAR = "war"
    GEOPOLITICS = "geopolitics"
    BUSINESS = "business"
    CRYPTO = "crypto"
    GENERAL_NEWS = "general_news"


ALL_SEGMENTS: tuple[str, ...] = tuple(s.value for s in ContentSegment)

_KEYWORD_MAP: list[tuple[str, ContentSegment]] = [
    (r"\b(crypto|bitcoin|btc|ethereum|blockchain|defi)\b", ContentSegment.CRYPTO),
    (r"\b(war|military|conflict|shelling|frontline|войн|фронт|обстрел)\b", ContentSegment.WAR),
    (r"\b(geopolit|sanction|nato|diplomacy|foreign.?affairs)\b", ContentSegment.GEOPOLITICS),
    (r"\b(politic|election|parliament|government|kremlin|дума|выбор)\b", ContentSegment.POLITICS),
    (r"\b(market|stock|equity|bond|s&p|nasdaq|moex|index|trading|рынок|акци)\b", ContentSegment.MARKETS),
    (r"\b(econom|macro|gdp|inflation|cpi|ставк|цб|fed|ecb)\b", ContentSegment.ECONOMY),
    (r"\b(tech|software|ai|startup|digital|chip|semiconductor|it)\b", ContentSegment.TECHNOLOGY),
    (r"\b(science|research|space|nasa|medicine|clinical|наук)\b", ContentSegment.SCIENCE),
    (r"\b(business|corporate|company|merger|ipo|enterprise|бизнес|компан)\b", ContentSegment.BUSINESS),
]

_ALIAS_MAP: dict[str, ContentSegment] = {
    "politics": ContentSegment.POLITICS,
    "political": ContentSegment.POLITICS,
    "markets": ContentSegment.MARKETS,
    "market": ContentSegment.MARKETS,
    "finance": ContentSegment.MARKETS,
    "financial": ContentSegment.MARKETS,
    "economy": ContentSegment.ECONOMY,
    "economic": ContentSegment.ECONOMY,
    "economics": ContentSegment.ECONOMY,
    "macro": ContentSegment.ECONOMY,
    "technology": ContentSegment.TECHNOLOGY,
    "tech": ContentSegment.TECHNOLOGY,
    "science": ContentSegment.SCIENCE,
    "war": ContentSegment.WAR,
    "conflict": ContentSegment.WAR,
    "geopolitics": ContentSegment.GEOPOLITICS,
    "geopolitical": ContentSegment.GEOPOLITICS,
    "business": ContentSegment.BUSINESS,
    "corporate": ContentSegment.BUSINESS,
    "crypto": ContentSegment.CRYPTO,
    "cryptocurrency": ContentSegment.CRYPTO,
    "general": ContentSegment.GENERAL_NEWS,
    "general_news": ContentSegment.GENERAL_NEWS,
    "news": ContentSegment.GENERAL_NEWS,
}


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _norm_token(raw: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(raw or "").strip().lower()).strip("_")


def _match_token(token: str) -> ContentSegment | None:
    if not token:
        return None
    if token in _ALIAS_MAP:
        return _ALIAS_MAP[token]
    for segment in ContentSegment:
        if token == segment.value or token.replace("-", "_") == segment.value:
            return segment
    text = token.replace("_", " ")
    for pattern, segment in _KEYWORD_MAP:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return segment
    return None


def _candidates_from_post(post: dict[str, Any]) -> list[str]:
    out: list[str] = []
    draft = post.get("draft")
    if isinstance(draft, dict):
        for key in ("topic", "category"):
            val = draft.get(key)
            if val:
                out.append(str(val))
    for key in ("topic", "category"):
        val = post.get(key)
        if val:
            out.append(str(val))
    cluster = post.get("cluster")
    if isinstance(cluster, dict) and cluster.get("category"):
        out.append(str(cluster["category"]))
    cluster_cat = post.get("cluster_category")
    if cluster_cat:
        out.append(str(cluster_cat))
    extras = post.get("draft_extras")
    if isinstance(extras, dict):
        if extras.get("topic"):
            out.append(str(extras["topic"]))
        if extras.get("category") and str(extras.get("category")) not in out:
            out.append(str(extras["category"]))
        cluster_ex = extras.get("cluster")
        if isinstance(cluster_ex, dict) and cluster_ex.get("category"):
            out.append(str(cluster_ex["category"]))
    elif isinstance(extras, str):
        parsed = _parse_json(extras)
        if parsed.get("topic"):
            out.append(str(parsed["topic"]))
        if parsed.get("category"):
            out.append(str(parsed["category"]))
        cluster_ex = parsed.get("cluster")
        if isinstance(cluster_ex, dict) and cluster_ex.get("category"):
            out.append(str(cluster_ex["category"]))
    if post.get("topic_bucket"):
        out.append(str(post["topic_bucket"]))
    return out


def classify_content_segment(post: dict[str, Any] | Any) -> str:
    """
    Classify post into content segment.
    Priority: draft.topic → draft.category → cluster.category → draft_extras.topic → general_news.
    """
    if not isinstance(post, dict):
        post = {"topic_bucket": str(getattr(post, "topic_bucket", "") or "")}
        extras = getattr(post, "draft_extras", None)
        if extras:
            post = {
                "draft_extras": extras,
                "topic_bucket": getattr(post, "topic_bucket", ""),
            }
    for raw in _candidates_from_post(post):
        token = _norm_token(raw)
        segment = _match_token(token)
        if segment is not None:
            return segment.value
        for part in token.split("_"):
            segment = _match_token(part)
            if segment is not None:
                return segment.value
    return ContentSegment.GENERAL_NEWS.value


def classify_from_draft_extras(extras_json: str | None, *, topic_bucket: str = "") -> str:
    post: dict[str, Any] = {"draft_extras": extras_json or "{}"}
    if topic_bucket:
        post["topic_bucket"] = topic_bucket
    return classify_content_segment(post)
