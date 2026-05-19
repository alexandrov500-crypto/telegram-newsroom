from __future__ import annotations

import re

_CHURN_RE = re.compile(
    r"\b(slightly|modestly|inch(ed|es)?|edge(s|d)?|little changed|unchanged|"
    r"holds steady|trades flat|marginal)\b",
    re.I,
)
_BAIT_RE = re.compile(
    r"\b(you won'?t believe|shocking|secret|must see|goes viral|"
    r"experts say|what happens next)\b",
    re.I,
)


def build_noise_warnings(
    *,
    editorial_priority_score: float,
    information_density: float,
    follow_up_kind: str | None,
    match_score: float,
    momentum: float,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if editorial_priority_score < 0.38:
        warnings.append("low editorial importance")
    if information_density < 0.4:
        warnings.append("low-signal update")
    if follow_up_kind in ("duplicate", "minor_variation"):
        warnings.append("repetitive market churn")
    if match_score >= 0.85:
        warnings.append("low novelty vs recent coverage")
    if momentum < 0.2 and editorial_priority_score < 0.5:
        warnings.append("stale storyline — limited new development")
    return tuple(warnings[:5])


def detect_shallow_rewrite(headline: str, summary: str | None) -> bool:
    text = f"{headline} {summary or ''}"
    if _BAIT_RE.search(text):
        return True
    if _CHURN_RE.search(text) and len((summary or "").split()) < 35:
        return True
    return False
