"""Explainable growth recommendations for drafts vs segment patterns."""

from __future__ import annotations

from typing import Any

from app.growth_layer.editorial.pattern_discovery import BOOLEAN_FEATURES, NUMERIC_FEATURES

_LIFT_THRESHOLD = 25.0
_NUMERIC_LIFT_THRESHOLD = 15.0

_BOOL_ACTIONS: dict[str, tuple[str, str, str]] = {
    "has_number": (
        "Consider adding a numeric element to the headline",
        "Avoid numeric headlines in this segment",
        "numbers in headlines",
    ),
    "has_percent": (
        "Include a percentage figure when relevant",
        "Reduce percentage-heavy headlines",
        "percentages in headlines",
    ),
    "has_currency": (
        "Currency figures may improve engagement in this segment",
        "Avoid currency-heavy headlines",
        "currency figures in headlines",
    ),
    "has_question": (
        "Question headlines can work in this segment",
        "Avoid question headlines",
        "question headlines",
    ),
    "has_colon": (
        "Colon-style headlines perform well in this segment",
        "Prefer single-clause headlines over colon splits",
        "colon-style headlines",
    ),
    "has_quote": (
        "Quoted headlines correlate with success in this segment",
        "Avoid long quotations in headlines",
        "quoted headlines",
    ),
}

_NUMERIC_ACTIONS: dict[str, tuple[str, str]] = {
    "headline_word_count": ("Adjust headline word count", "headline word count"),
    "headline_length": ("Adjust headline length", "headline length"),
    "paragraph_count": ("Adjust paragraph count", "paragraph count"),
    "link_count": ("Reduce link count", "links"),
    "emoji_count": ("Adjust emoji usage", "emojis"),
    "body_length": ("Adjust body length", "body length"),
    "bullet_count": ("Adjust bullet count", "bullets"),
    "source_count": ("Adjust source count", "sources"),
}


def _format_pct(rate: float) -> str:
    return f"{round(rate * 100)}%"


def _format_lift(lift: float | None) -> str:
    if lift is None:
        return ""
    sign = "+" if lift >= 0 else ""
    return f"{sign}{round(lift)}%"


def _boolean_evidence(
    segment: str,
    label: str,
    pattern: dict[str, Any],
    *,
    metric: str = "err",
) -> str:
    lift = pattern.get("lift")
    top = float(pattern.get("top") or 0)
    bottom = float(pattern.get("bottom") or 0)
    seg = segment.replace("_", " ").title()
    metric_label = metric.upper() if metric == "err" else metric
    lift_txt = _format_lift(lift) if lift is not None else ""
    return (
        f"{seg} posts with {label} showed {lift_txt} {metric_label} lift historically "
        f"(top {_format_pct(top)} vs bottom {_format_pct(bottom)})."
    )


def _numeric_evidence(
    segment: str,
    label: str,
    pattern: dict[str, Any],
    current: float,
    *,
    metric: str = "err",
) -> str:
    rng = pattern.get("top_range") or {}
    lo, hi = rng.get("low"), rng.get("high")
    lift = pattern.get("lift")
    seg = segment.replace("_", " ").title()
    metric_label = metric.upper() if metric == "err" else metric
    lift_txt = _format_lift(lift) if lift is not None else ""
    if lo is not None and hi is not None:
        if current > float(hi):
            return (
                f"Posts with >{hi} {label} showed lower {metric_label} "
                f"(winning range {lo}–{hi}, {lift_txt} lift vs bottom cohort)."
            )
        if current < float(lo):
            return (
                f"{seg} top posts used {label} around {lo}–{hi} "
                f"({lift_txt} {metric_label} lift historically)."
            )
    return f"{seg} top posts favor specific {label} ranges ({lift_txt} {metric_label} lift historically)."


def _format_range(rng: dict[str, Any]) -> str:
    lo, hi = rng.get("low"), rng.get("high")
    if lo is None or hi is None:
        return ""
    if lo == hi:
        return str(lo)
    return f"{lo}–{hi}"


def generate_growth_recommendations(
    analysis: dict[str, Any],
    *,
    discovery: dict[str, Any],
    segment: str | None = None,
    metric: str = "err",
    runtime_dir: str | None = None,
    policy_registry: dict[str, Any] | None = None,
    apply_policy: bool = True,
) -> dict[str, Any]:
    """
    Compare draft features against segment winning/anti patterns.
    Every recommendation includes statistical evidence from discovery data.
    """
    segment_name = str(segment or analysis.get("content_segment") or "general_news")
    features = analysis.get("features") if isinstance(analysis.get("features"), dict) else analysis
    patterns = discovery.get("patterns") or {}
    numeric = discovery.get("numeric_patterns") or {}
    sample_size = int(discovery.get("sample_size") or 0)

    recommendations: list[str] = []
    detailed: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []

    if sample_size < 5:
        return {
            "recommendations": [],
            "recommendations_detailed": [],
            "mismatches": [],
            "insufficient_data": True,
            "sample_size": sample_size,
        }

    for feat in BOOLEAN_FEATURES:
        block = patterns.get(feat) or {}
        lift = block.get("lift")
        if lift is None:
            continue
        current = bool(features.get(feat))
        top = float(block.get("top") or 0)
        bottom = float(block.get("bottom") or 0)
        preferred = top >= bottom
        pos, neg, label = _BOOL_ACTIONS.get(feat, (feat, feat, feat.replace("_", " ")))

        if lift >= _LIFT_THRESHOLD and preferred and not current:
            evidence = _boolean_evidence(segment_name, label, block, metric=metric)
            text = f"{pos} — {evidence}"
            recommendations.append(text)
            detailed.append({"text": pos, "evidence": evidence, "feature": feat})
            mismatches.append({"feature": feat, "current": current, "preferred": True, "lift": lift})
        elif lift <= -_LIFT_THRESHOLD and not preferred and current:
            evidence = _boolean_evidence(segment_name, label, block, metric=metric)
            text = f"{neg} — {evidence}"
            recommendations.append(text)
            detailed.append({"text": neg, "evidence": evidence, "feature": feat})
            mismatches.append({"feature": feat, "current": current, "preferred": False, "lift": lift})

    for feat in NUMERIC_FEATURES:
        block = numeric.get(feat) or {}
        lift = block.get("lift")
        if lift is None or abs(float(lift)) < _NUMERIC_LIFT_THRESHOLD:
            continue
        current = float(features.get(feat) or 0)
        rng = block.get("top_range") or {}
        lo, hi = rng.get("low"), rng.get("high")
        if lo is None or hi is None:
            continue
        if float(lo) <= current <= float(hi):
            continue
        action, label = _NUMERIC_ACTIONS.get(feat, (f"Adjust {feat.replace('_', ' ')}", feat.replace("_", " ")))
        range_txt = _format_range(rng)
        if feat == "paragraph_count":
            action = f"{segment_name.replace('_', ' ').title()} posts perform best with {range_txt} paragraphs"
        elif feat == "link_count" and current > float(hi):
            action = f"Reduce links from {int(current)} to {int(hi)} or fewer"
        elif feat == "headline_word_count":
            action = f"Keep headline word count within {range_txt}"
        evidence = _numeric_evidence(segment_name, label, block, current, metric=metric)
        text = f"{action} — {evidence}"
        recommendations.append(text)
        detailed.append({"text": action, "evidence": evidence, "feature": feat})
        mismatches.append(
            {
                "feature": feat,
                "current": current,
                "preferred_range": {"low": lo, "high": hi},
                "lift": lift,
            }
        )

    result = {
        "recommendations": recommendations[:8],
        "recommendations_detailed": detailed[:8],
        "mismatches": mismatches[:12],
        "insufficient_data": False,
        "sample_size": sample_size,
    }

    if apply_policy:
        from app.growth_layer.policy.policy_registry import load_policy_registry
        from app.growth_layer.policy.recommendation_policy import apply_recommendation_policy

        registry = policy_registry if policy_registry is not None else load_policy_registry(runtime_dir)
        if registry.get("recommendations") or registry.get("segments"):
            result = apply_recommendation_policy(
                result,
                registry=registry,
                segment=segment_name,
            )

    return result
