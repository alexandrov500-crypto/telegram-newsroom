"""Advisory bundle — compose intelligence for desk + draft extras."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from app.editorial.desk_filter import DeskDecision
from app.editorial.intelligence.fatigue import compute_topic_fatigue, fatigue_enabled, fatigue_suppress_threshold
from app.editorial.intelligence.headline_intel import evaluate_headline_intelligence
from app.editorial.intelligence.memory import memory_snapshot, topic_key_from_text
from app.editorial.intelligence.reputation_evolution import source_usefulness_snapshot
from app.editorial.intelligence.sandbox import active_experiments
from app.editorial.intelligence.variety import compute_variety_score


@dataclass(frozen=True)
class EditorialAdvisory:
    topic_key: str
    fatigue_score: float
    variety_score: float
    headline_score: float
    priority_adjustment: float  # subtract from desk quality (advisory)
    suppress_recommended: bool
    reasons: tuple[str, ...]
    source_usefulness: dict[str, Any]
    experiments: dict[str, bool]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_editorial_advisory(
    *,
    text: str,
    sources: list[str],
    runtime_dir: str,
    topic_key: str | None = None,
    headline: str = "",
) -> EditorialAdvisory:
    key = topic_key or topic_key_from_text(text, fallback="cluster")
    fatigue = compute_topic_fatigue(runtime_dir, text=text, topic_key=key) if fatigue_enabled() else {
        "fatigue_score": 0.0,
        "reasons": [],
    }
    variety = compute_variety_score(text, runtime_dir=runtime_dir, headline=headline)
    mem = memory_snapshot(runtime_dir)
    recent_h = [
        str((mem.get("topics") or {}).get(k, {}).get("last_headline") or "")
        for k in list((mem.get("topics") or {}).keys())[:15]
    ]
    hl = evaluate_headline_intelligence(headline, body_excerpt=text[:400], recent_headlines=recent_h)
    reasons = list(fatigue.get("reasons") or []) + list(variety.get("warnings") or [])
    f_score = float(fatigue.get("fatigue_score") or 0.0)
    v_score = float(variety.get("variety_score") or 0.82)
    priority_adj = round(f_score * 18 + (1.0 - v_score) * 12, 2)
    suppress = f_score >= fatigue_suppress_threshold() and os.getenv(
        "EDITORIAL_FATIGUE_SUPPRESS", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    return EditorialAdvisory(
        topic_key=key,
        fatigue_score=f_score,
        variety_score=v_score,
        headline_score=float(hl.get("score") or 0.0),
        priority_adjustment=priority_adj,
        suppress_recommended=suppress,
        reasons=tuple(reasons[:12]),
        source_usefulness=source_usefulness_snapshot(runtime_dir, sources),
        experiments=active_experiments(),
    )


def apply_advisory_to_desk(desk: DeskDecision, advisory: EditorialAdvisory) -> DeskDecision:
    """Advisory-only desk adjustment (never bypasses hard rejects)."""
    if not desk.publish:
        return desk
    if advisory.suppress_recommended and not desk.breaking_override:
        return DeskDecision(
            publish=False,
            reason=f"advisory_fatigue:{','.join(advisory.reasons[:3])}",
            editorial_category=desk.editorial_category,
            quality_score=desk.quality_score,
            priority_tier="reject",
            breaking_override=desk.breaking_override,
        )
    q = max(0.0, desk.quality_score - advisory.priority_adjustment)
    tier = desk.priority_tier
    if advisory.priority_adjustment >= 10 and tier == "priority":
        tier = "lower"
    return DeskDecision(
        publish=desk.publish,
        reason=desk.reason if tier == desk.priority_tier else f"{desk.reason}+advisory_downrank",
        editorial_category=desk.editorial_category,
        quality_score=round(q, 2),
        priority_tier=tier,
        breaking_override=desk.breaking_override,
    )
