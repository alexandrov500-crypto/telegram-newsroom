"""Contextual CTA — zero-spam, reference-first."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.product_os.content_format import ContentFormat


class CTAType(str, Enum):
    NONE = "none"
    MINIMAL = "minimal"
    INSIGHT = "insight"
    EXPLAINER = "explainer"
    DIGEST = "digest"


@dataclass(frozen=True)
class ContextualCTA:
    cta_type: CTAType
    line: str
    enable_share: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "cta_type": self.cta_type.value,
            "line": self.line,
            "enable_share": self.enable_share,
        }


def select_contextual_cta(
    *,
    content_format: ContentFormat,
    is_breaking: bool = False,
    reference_forward_score: float = 0.0,
    trigger_forward: bool = False,
) -> ContextualCTA:
    if is_breaking or content_format == ContentFormat.SIGNAL:
        return ContextualCTA(CTAType.NONE, "", False)

    if content_format == ContentFormat.DIGEST:
        return ContextualCTA(
            CTAType.DIGEST,
            "Это заменяет 10 каналов на сегодня — сохраните или перешлите.",
            enable_share=True,
        )

    if content_format in {ContentFormat.MODEL, ContentFormat.CONTEXT}:
        return ContextualCTA(
            CTAType.EXPLAINER,
            "Сохраните — это объяснение будет актуально.",
            enable_share=reference_forward_score >= 55,
        )

    if content_format == ContentFormat.INSIGHT or trigger_forward:
        return ContextualCTA(
            CTAType.INSIGHT,
            "Перешлите коллеге, если это влияет на вашу сферу.",
            enable_share=True,
        )

    if reference_forward_score >= 60:
        return ContextualCTA(
            CTAType.INSIGHT,
            "Перешлите коллеге, если это влияет на вашу сферу.",
            enable_share=True,
        )

    return ContextualCTA(CTAType.MINIMAL, "", False)
