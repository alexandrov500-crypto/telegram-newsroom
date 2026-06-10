"""Aggressive growth mechanics — discovery, hashtags, forward hooks (no spam)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.mpaes.config import growth_aggression_level
from app.editorial.mpaes.hub_substitution_map import infer_vertical
from app.editorial.mpaes.persona_registry import DemographicSegment


@dataclass(frozen=True)
class GrowthAcquisitionPlan:
    discovery_hashtags: tuple[str, ...]
    forward_hook: str | None
    share_nudge: bool
    acquisition_channel: str
    aggression: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "discovery_hashtags": list(self.discovery_hashtags),
            "forward_hook": self.forward_hook,
            "share_nudge": self.share_nudge,
            "acquisition_channel": self.acquisition_channel,
            "aggression": self.aggression,
        }


_VERTICAL_TAGS: dict[str, str] = {
    "macro": "#MacroFlow",
    "markets": "#MarketShock",
    "geopolitics": "#GeoShift",
    "ai": "#AIDisruption",
    "crypto": "#MacroFlow",
    "local": "#GlobalSignal",
    "business": "#TechSignal",
    "energy": "#GlobalSignal",
    "science": "#TechSignal",
}

_SEGMENT_FORWARD: dict[DemographicSegment, str] = {
    DemographicSegment.HUB_MALE: "Перешлите, если влияет на ваши решения по рынку и риску.",
    DemographicSegment.HUB_FEMALE: "Сохраните — пригодится для контекста недели и планирования.",
    DemographicSegment.REFERENCE_OPERATOR_MALE: "Один пост вместо 10 каналов — перешлите, если полезно.",
}


def build_growth_acquisition_plan(
    text: str,
    *,
    editorial_category: str = "",
    primary_segment: DemographicSegment = DemographicSegment.REFERENCE_OPERATOR_MALE,
    substitution_score: float = 50.0,
    is_breaking: bool = False,
    reference_forward_score: float = 0.0,
) -> GrowthAcquisitionPlan:
    vertical = infer_vertical(text, editorial_category)
    aggression = growth_aggression_level()

    tags: list[str] = [_VERTICAL_TAGS.get(vertical, "#GlobalSignal")]
    if substitution_score >= 70 and "#HubDigest" not in tags:
        tags.append("#HubDigest")
    if aggression == "high" and substitution_score >= 60:
        cross = "#MustRead" if reference_forward_score >= 65 else None
        if cross and len(tags) < 2:
            tags.append(cross)

    forward_hook: str | None = None
    share_nudge = False

    if is_breaking:
        forward_hook = None
        share_nudge = False
    elif substitution_score >= 75 or reference_forward_score >= 70:
        forward_hook = _SEGMENT_FORWARD.get(primary_segment, _SEGMENT_FORWARD[DemographicSegment.REFERENCE_OPERATOR_MALE])
        share_nudge = aggression in {"medium", "high"}
    elif aggression == "high" and substitution_score >= 55:
        forward_hook = "Один канал вместо десятка — сохраните, если закрывает ваш информационный стек."
        share_nudge = True

    acquisition = "reference_forward" if share_nudge else "organic_discovery"

    return GrowthAcquisitionPlan(
        discovery_hashtags=tuple(tags[:2]),
        forward_hook=forward_hook,
        share_nudge=share_nudge,
        acquisition_channel=acquisition,
        aggression=aggression,
    )


def apply_discovery_hashtags(body: str, plan: GrowthAcquisitionPlan) -> tuple[str, dict[str, Any]]:
    text = (body or "").strip()
    meta: dict[str, Any] = {"applied": False, "tags": []}
    if not text or not plan.discovery_hashtags:
        return text, meta

    stripped = re.sub(r"#\w+", "", text).strip()
    existing = set(re.findall(r"#\w+", text))
    to_add = [t for t in plan.discovery_hashtags if t not in existing]
    if not to_add:
        return text, meta

    out = f"{stripped}\n\n" + " ".join(to_add[:2])
    meta = {"applied": True, "tags": to_add[:2]}
    return out.strip(), meta
