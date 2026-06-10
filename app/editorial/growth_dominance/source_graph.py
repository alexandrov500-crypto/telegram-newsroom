"""Source Graph Model — independence and cross-class reinforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.source_tiers import classify_source


def _source_class(channel: str, *, runtime_dir: str | None = None) -> str:
    tier, _auth = classify_source(channel, runtime_dir=runtime_dir)
    if tier == 1:
        return "wire_official"
    if tier == 2:
        handle = (channel or "").strip().lower().lstrip("@")
        if handle in {"cb_economics", "banksta", "vedomosti", "rbc_news", "thebell_io", "tnews365"}:
            return "ru_business_tg"
        return "curated_editorial"
    return "signal_t3"


@dataclass(frozen=True)
class SourceGraphEvaluation:
    unique_classes: int
    classes: tuple[str, ...]
    independence_score: float
    single_class_only: bool
    reinforcement: float
    downgrade_to_digest: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "unique_classes": self.unique_classes,
            "classes": list(self.classes),
            "independence_score": round(self.independence_score, 4),
            "single_class_only": self.single_class_only,
            "reinforcement": round(self.reinforcement, 4),
            "downgrade_to_digest": self.downgrade_to_digest,
            "reason": self.reason,
        }


def evaluate_cluster_source_graph(
    channels: list[str],
    *,
    runtime_dir: str | None = None,
    cluster_size: int = 1,
) -> SourceGraphEvaluation:
    classes: list[str] = []
    for ch in channels:
        ck = _source_class(ch, runtime_dir=runtime_dir)
        if ck not in classes:
            classes.append(ck)

    unique = len(classes)
    single = unique <= 1 and len(channels) >= 1
    reinforcement = min(1.0, unique / max(1, len(set(channels))))
    independence = 1.0 if unique >= 2 else (0.55 if cluster_size == 1 else 0.75)

    from app.editorial.growth_dominance.config import require_multi_source_class

    downgrade = require_multi_source_class() and single and cluster_size >= 1

    reason = "multi_class_ok"
    if downgrade:
        reason = "single_class_downgrade_digest"
    elif single:
        reason = "single_class_cluster"

    return SourceGraphEvaluation(
        unique_classes=unique,
        classes=tuple(classes),
        independence_score=independence,
        single_class_only=single,
        reinforcement=reinforcement,
        downgrade_to_digest=downgrade,
        reason=reason,
    )
