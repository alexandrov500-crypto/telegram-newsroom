"""Editorial identity enforcement — score + gate."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.identity.differentiation import evaluate_differentiation
from app.identity.insight_layer import score_insight_depth
from app.identity.style_guide import detect_vertical, score_style_alignment


@dataclass(frozen=True)
class EditorialIdentityVerdict:
    allowed: bool
    style_score: float
    insight_score: float
    differentiation_ok: bool
    reason: str


def _enabled() -> bool:
    return os.getenv("EDITORIAL_IDENTITY_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def evaluate_editorial_identity(
    content: str,
    *,
    runtime_dir: str,
    vertical: str = "",
) -> EditorialIdentityVerdict:
    if not _enabled():
        return EditorialIdentityVerdict(True, 1.0, 1.0, True, "disabled")

    v = detect_vertical(content, vertical)
    style = score_style_alignment(content, vertical=v)
    insight = score_insight_depth(content)
    diff = evaluate_differentiation(content, runtime_dir=runtime_dir)

    min_style = float(os.getenv("EDITORIAL_IDENTITY_MIN_STYLE", "0.58"))
    min_insight = float(os.getenv("EDITORIAL_IDENTITY_MIN_INSIGHT", "0.45"))

    allowed = style.aligned and insight >= min_insight and diff.unique
    reason = style.reason
    if insight < min_insight:
        reason = "shallow_insight"
        allowed = False
    if not diff.unique:
        reason = diff.reason
        allowed = False

    return EditorialIdentityVerdict(
        allowed=allowed,
        style_score=style.score,
        insight_score=insight,
        differentiation_ok=diff.unique,
        reason=reason,
    )
