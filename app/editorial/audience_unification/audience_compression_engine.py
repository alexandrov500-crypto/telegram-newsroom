"""Audience Compression Engine — merge cluster signals into one narrative."""

from __future__ import annotations

import re
from typing import Any


def compress_cluster_narrative(
    texts: list[str],
    *,
    topic_hint: str = "",
) -> tuple[str, dict[str, Any]]:
    """
    Rule-based compression: strongest lead + deduped bullets + single mental model.
    Stateless — no LLM.
    """
    clean = [t.strip() for t in texts if (t or "").strip()]
    meta: dict[str, Any] = {"input_count": len(clean), "compressed": False}
    if not clean:
        return "", meta
    if len(clean) == 1:
        return clean[0], meta

    leads: list[str] = []
    seen: set[str] = set()
    for raw in clean:
        first = raw.split("\n")[0].strip()[:280]
        key = re.sub(r"\W+", "", first.lower())[:80]
        if key and key not in seen:
            seen.add(key)
            leads.append(first)

    topic = (topic_hint or "ключевая тема").replace("_", " ")[:60]
    headline = leads[0] if leads else clean[0][:200]
    bullets = []
    for i, lead in enumerate(leads[1:4], start=1):
        bullets.append(f"{i}. {lead}")

    body = (
        f"{headline}\n\n"
        f"Единая картина по теме «{topic}»:\n\n"
        + ("\n".join(bullets) if bullets else f"• {headline}")
        + "\n\n"
        "Вывод: несколько сигналов сходятся — это одна история, а не поток мелких новостей.\n\n"
        "Почему важно: экономит время и заменяет несколько каналов одним объяснением.\n\n"
        "Что дальше: следим за подтверждением главного сигнала."
    )
    meta["compressed"] = True
    meta["merged_signals"] = len(leads)
    return body.strip(), meta
