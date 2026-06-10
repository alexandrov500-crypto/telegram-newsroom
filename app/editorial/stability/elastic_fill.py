"""Elastic fill — buffer desk-approved clusters for anti-pause recontextualization."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from app.editorial.stability.config import elastic_cluster_max_age_hours
from app.editorial.stability.state import load_state, save_state


@dataclass(frozen=True)
class BufferedCluster:
    fingerprint: str
    combined_text: str
    sources: tuple[str, ...]
    topic_hint: str
    editorial_category: str
    quality_score: float
    ts_unix: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "combined_text": self.combined_text[:4000],
            "sources": list(self.sources),
            "topic_hint": self.topic_hint,
            "editorial_category": self.editorial_category,
            "quality_score": self.quality_score,
            "ts_unix": self.ts_unix,
        }


def record_cluster_buffer(
    runtime_dir: str | None,
    *,
    fingerprint: str,
    combined_text: str,
    sources: list[str],
    topic_hint: str,
    editorial_category: str,
    quality_score: float,
) -> None:
    data = load_state(runtime_dir)
    buf = list(data.get("cluster_buffer") or [])
    entry = BufferedCluster(
        fingerprint=fingerprint,
        combined_text=combined_text,
        sources=tuple(sources[:8]),
        topic_hint=topic_hint,
        editorial_category=editorial_category,
        quality_score=quality_score,
        ts_unix=time.time(),
    ).to_dict()
    buf = [b for b in buf if isinstance(b, dict) and b.get("fingerprint") != fingerprint]
    buf.append(entry)
    max_age = elastic_cluster_max_age_hours() * 3600.0
    now = time.time()
    buf = [b for b in buf if isinstance(b, dict) and now - float(b.get("ts_unix") or 0) <= max_age]
    data["cluster_buffer"] = buf[-24:]
    save_state(runtime_dir, data)


def pick_elastic_cluster(
    runtime_dir: str | None,
    *,
    exclude_fingerprint: str = "",
) -> BufferedCluster | None:
    data = load_state(runtime_dir)
    buf = list(data.get("cluster_buffer") or [])
    max_age = elastic_cluster_max_age_hours() * 3600.0
    now = time.time()
    candidates: list[BufferedCluster] = []
    for raw in buf:
        if not isinstance(raw, dict):
            continue
        if now - float(raw.get("ts_unix") or 0) > max_age:
            continue
        fp = str(raw.get("fingerprint") or "")
        if exclude_fingerprint and fp == exclude_fingerprint:
            continue
        candidates.append(
            BufferedCluster(
                fingerprint=fp,
                combined_text=str(raw.get("combined_text") or ""),
                sources=tuple(raw.get("sources") or []),
                topic_hint=str(raw.get("topic_hint") or ""),
                editorial_category=str(raw.get("editorial_category") or "macro"),
                quality_score=float(raw.get("quality_score") or 0.0),
                ts_unix=float(raw.get("ts_unix") or 0),
            )
        )
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c.quality_score, -c.ts_unix))
    return candidates[0]


def build_context_post_from_buffer(cluster: BufferedCluster) -> str:
    """Rule-based recontextualization — no extra LLM call required."""
    lead = cluster.combined_text.strip().split("\n")[0][:280]
    topic = cluster.topic_hint.replace("_", " ")[:60] or "рынки и экономика"
    src = cluster.sources[0] if cluster.sources else "редакция"
    return (
        f"Контекст: {topic}\n\n"
        f"{lead}\n\n"
        f"• Что произошло: ключевое событие по теме «{topic}».\n"
        f"• Почему важно: влияет на решения инвесторов и бизнеса.\n"
        f"• Что дальше: следим за подтверждением и реакцией рынков.\n\n"
        f"Источник: {src}"
    )
