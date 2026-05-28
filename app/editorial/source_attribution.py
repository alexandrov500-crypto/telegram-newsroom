"""Tier-based source attribution for public channel posts."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.editorial.source_tiers import SourceTierInfo, aggregate_source_tier

_URL_RE = re.compile(r"https?://\S+")


@dataclass(frozen=True)
class SourceAttribution:
    tier: int
    footer: str | None
    mandatory: bool
    strip_urls_from_body: bool

    @property
    def include_footer(self) -> bool:
        return bool(self.footer)


def _display_name(handle: str | None) -> str:
    h = (handle or "").strip()
    if not h:
        return "источник"
    return h if h.startswith("@") else f"@{h.lstrip('@')}"


def resolve_source_attribution(
    sources: list[str] | None,
    *,
    runtime_dir: str | None = None,
    compact_tier1: bool | None = None,
) -> SourceAttribution:
    """
    Tier 1: optional compact attribution (footer omitted when compact_tier1).
    Tier 2: short footer «Источник: {name}».
    Tier 3: mandatory explicit attribution; strip raw URLs from body.
    Policy driven by editorial_tuning.yaml (style: source | via | hidden).
    """
    from app.editorial.tuning_loader import get_editorial_tuning

    attr_cfg = get_editorial_tuning().attribution
    style = attr_cfg.style
    compact = attr_cfg.tier1_compact if compact_tier1 is None else compact_tier1
    tier_info = aggregate_source_tier(sources, runtime_dir=runtime_dir)
    name = _display_name(tier_info.primary_handle)

    if style == "hidden":
        return SourceAttribution(tier=tier_info.tier, footer=None, mandatory=False, strip_urls_from_body=False)

    if tier_info.tier == 1:
        if style == "via":
            footer = f"via {name}" if name else None
        elif compact:
            footer = None
        else:
            footer = f"Источник: {name}" if name else None
        return SourceAttribution(tier=1, footer=footer, mandatory=False, strip_urls_from_body=False)

    if tier_info.tier == 2:
        if style == "via":
            footer = f"via {name}" if name else None
        else:
            footer = f"Источник: {name}"
        return SourceAttribution(
            tier=2,
            footer=footer,
            mandatory=False,
            strip_urls_from_body=False,
        )

    footer = f"via {name}" if style == "via" else f"Источник: {name}"
    return SourceAttribution(
        tier=3,
        footer=footer,
        mandatory=style != "hidden",
        strip_urls_from_body=True,
    )


def strip_raw_urls(text: str) -> str:
    t = _URL_RE.sub("", text or "")
    return re.sub(r"[ \t]{2,}", " ", t).strip()


def apply_attribution_to_footer(
    existing_footer: str | None,
    attribution: SourceAttribution,
) -> str | None:
    """Prefer tier policy footer; keep existing only when policy has no footer."""
    if attribution.footer:
        return attribution.footer
    if attribution.mandatory and not existing_footer:
        return "Источник: —"
    return existing_footer
