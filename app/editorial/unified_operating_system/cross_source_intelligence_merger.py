"""Cross-Source Intelligence Merger (CSIM) — world signal from multiple clusters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_EVENT_DEDUP_KEY = re.compile(r"\W+")


@dataclass(frozen=True)
class CSIMResult:
    body: str
    intelligence_score: float
    merged_events: int
    deduped_sources: int
    same_event_detected: bool
    meta: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "intelligence_score": round(self.intelligence_score, 2),
            "merged_events": self.merged_events,
            "deduped_sources": self.deduped_sources,
            "same_event_detected": self.same_event_detected,
            **self.meta,
        }


def _normalize_key(text: str) -> str:
    first = (text or "").split("\n")[0][:200].lower()
    return _EVENT_DEDUP_KEY.sub("", first)[:80]


def _overlap_ratio(a: str, b: str) -> float:
    wa = set((a or "").lower().split())
    wb = set((b or "").lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / max(1, len(wa | wb))


def merge_world_signal(
    texts: list[str],
    *,
    topic_hint: str = "",
) -> CSIMResult:
    clean = [t.strip() for t in texts if (t or "").strip()]
    meta: dict[str, Any] = {"format": "world_signal", "compressed": False}

    if not clean:
        return CSIMResult("", 0.0, 0, 0, False, meta)
    if len(clean) == 1:
        score = _score_single(clean[0])
        return CSIMResult(clean[0], score, 1, 1, False, meta)

    leads: list[str] = []
    seen: set[str] = set()
    same_event = False
    for i, raw in enumerate(clean):
        key = _normalize_key(raw)
        if key and key in seen:
            same_event = True
            continue
        if key:
            seen.add(key)
        for prev in clean[:i]:
            if _overlap_ratio(raw, prev) >= 0.45:
                same_event = True
                break
        first = raw.split("\n")[0].strip()[:280]
        if first:
            leads.append(first)

    topic = (topic_hint or "global signal").replace("_", " ")[:60]
    headline = leads[0] if leads else clean[0][:200]

    body = (
        f"{headline}\n\n"
        f"Что произошло: несколько источников фиксируют одну линию по теме «{topic}».\n\n"
        f"Почему важно: это сигнал для решений по рынкам, технологиям и геополитике.\n\n"
        f"Глобальный контекст: событие выходит за рамки одного домена — "
        f"связано с макро, AI и/или международной повесткой.\n\n"
        f"Связь доменов: "
        + _cross_domain_line(headline)
        + "\n\n"
        f"Ментальная модель: {len(leads)} сигналов → одна история, не лента мелких новостей."
    )

    if len(leads) > 1:
        bullets = "\n".join(f"• {lead}" for lead in leads[1:4])
        body += f"\n\nДополнительные углы:\n{bullets}"

    meta["compressed"] = True
    score = min(100.0, 40.0 + len(leads) * 12.0 + (15 if same_event else 0) + len(clean) * 3.0)

    return CSIMResult(
        body=body.strip(),
        intelligence_score=score,
        merged_events=len(leads),
        deduped_sources=len(seen),
        same_event_detected=same_event,
        meta=meta,
    )


def _cross_domain_line(text: str) -> str:
    t = text or ""
    parts: list[str] = []
    if re.search(r"(fed|ставк|cpi|macro|инфляц)", t, re.I):
        parts.append("рынки и макро")
    if re.search(r"(ai|openai|tech|нейросет)", t, re.I):
        parts.append("AI/tech")
    if re.search(r"(sanction|war|геополит|nato)", t, re.I):
        parts.append("геополитика")
    if re.search(r"(crypto|btc|биткоин)", t, re.I):
        parts.append("crypto")
    if not parts:
        parts = ["макро", "бизнес", "глобальный контекст"]
    return " + ".join(parts[:3])


def _score_single(text: str) -> float:
    words = len((text or "").split())
    domains = sum(
        1
        for pat in (
            r"(fed|macro|ставк)",
            r"(ai|openai|tech)",
            r"(sanction|war|геополит)",
            r"(market|рынок|moex)",
        )
        if re.search(pat, text, re.I)
    )
    return min(100.0, 35.0 + words * 0.8 + domains * 12.0)
