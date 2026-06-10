"""Detect whether pre-publication recommendations were adopted in the published post."""

from __future__ import annotations

from typing import Any

from app.growth_layer.editorial.feature_extraction import extract_editorial_features

FEATURE_TO_TYPE: dict[str, str] = {
    "has_number": "headline_number",
    "has_percent": "headline_percent",
    "has_currency": "headline_currency",
    "has_question": "reduce_questions",
    "has_colon": "headline_colon",
    "has_quote": "reduce_quotes",
    "headline_word_count": "headline_word_count",
    "headline_length": "headline_length",
    "paragraph_count": "paragraph_count",
    "link_count": "reduce_links",
    "emoji_count": "emoji_usage",
    "body_length": "body_length",
    "bullet_count": "bullet_count",
    "source_count": "source_count",
}


def recommendation_type_for_feature(feature: str) -> str:
    return FEATURE_TO_TYPE.get(str(feature), str(feature))


def _draft_features(advice: dict[str, Any]) -> dict[str, Any]:
    feats = advice.get("features")
    if isinstance(feats, dict):
        return feats
    return {}


def _published_features(published_post: dict[str, Any]) -> dict[str, Any]:
    has_content = bool(
        published_post.get("content")
        or published_post.get("editor_title")
        or published_post.get("editor_summary")
        or published_post.get("body")
    )
    if has_content:
        return extract_editorial_features(published_post)
    if any(k in published_post for k in FEATURE_TO_TYPE):
        return published_post
    return extract_editorial_features(published_post)


def _mismatch_map(advice: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in advice.get("mismatches") or []:
        if isinstance(item, dict) and item.get("feature"):
            out[str(item["feature"])] = item
    return out


def _boolean_adopted(
    *,
    feature: str,
    draft_val: bool,
    published_val: bool,
    mismatch: dict[str, Any] | None,
) -> bool:
    preferred = mismatch.get("preferred") if mismatch else None
    if preferred is True:
        return (not draft_val) and published_val
    if preferred is False:
        return draft_val and (not published_val)
    return draft_val != published_val and published_val != draft_val


def _numeric_adopted(
    *,
    draft_val: float,
    published_val: float,
    mismatch: dict[str, Any] | None,
) -> bool:
    if not mismatch:
        return False
    rng = mismatch.get("preferred_range") or {}
    lo, hi = rng.get("low"), rng.get("high")
    if lo is None or hi is None:
        return False
    lo_f, hi_f = float(lo), float(hi)
    draft_dist = 0.0
    if draft_val < lo_f:
        draft_dist = lo_f - draft_val
    elif draft_val > hi_f:
        draft_dist = draft_val - hi_f
    pub_dist = 0.0
    if published_val < lo_f:
        pub_dist = lo_f - published_val
    elif published_val > hi_f:
        pub_dist = published_val - hi_f
    if draft_dist <= 0:
        return False
    if pub_dist <= 0:
        return True
    return pub_dist < draft_dist - 1e-9


def detect_recommendation_adoption(
    advice: dict[str, Any],
    published_post: dict[str, Any],
    *,
    draft_features: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    For each recommendation in advice, determine if the published post reflects it.
    Compares advice-time draft features vs published post features.
    """
    draft = draft_features if draft_features is not None else _draft_features(advice)
    published = _published_features(published_post)
    mismatches = _mismatch_map(advice)
    detailed = advice.get("recommendations_detailed") or []
    if not detailed:
        return []

    results: list[dict[str, Any]] = []
    for item in detailed:
        if not isinstance(item, dict):
            continue
        feature = str(item.get("feature") or "")
        if not feature:
            continue
        rec_type = recommendation_type_for_feature(feature)
        mismatch = mismatches.get(feature)
        draft_raw = draft.get(feature)
        pub_raw = published.get(feature)

        if feature.startswith("has_") or isinstance(draft_raw, bool):
            adopted = _boolean_adopted(
                feature=feature,
                draft_val=bool(draft_raw),
                published_val=bool(pub_raw),
                mismatch=mismatch,
            )
        else:
            adopted = _numeric_adopted(
                draft_val=float(draft_raw or 0),
                published_val=float(pub_raw or 0),
                mismatch=mismatch,
            )

        results.append(
            {
                "recommendation": rec_type,
                "recommendation_type": rec_type,
                "feature": feature,
                "text": str(item.get("text") or ""),
                "adopted": bool(adopted),
                "draft_value": draft_raw,
                "published_value": pub_raw,
            }
        )
    return results
