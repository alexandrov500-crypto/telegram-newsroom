"""Machine-readable draft explainability (governance layer)."""

from __future__ import annotations

from typing import Any

from editorial.governance.diversity_controls import diversity_metrics
from editorial.governance.policies_engine import evaluate_policies
from editorial.governance.ranking import RankingTrace
from editorial.governance.reputation import explainable_reputation
from editorial.policy import dominant_channel_key
from db.models import RawPost


def build_draft_governance_metadata(
    *,
    runtime_dir: str | None,
    posts: list[RawPost],
    topic_hint: str,
    fingerprint: str,
    ranking_trace: RankingTrace | dict[str, Any] | None,
    pipeline_decision: dict[str, Any] | None,
    policy_matches: list[dict[str, Any]] | None = None,
    selection_reasons: list[str] | None = None,
    suppression_bypasses: list[str] | None = None,
) -> dict[str, Any]:
    chans = [str(p.channel_name or "").strip().lower() for p in posts if str(p.channel_name or "").strip()]
    dom = dominant_channel_key(posts)
    rep = explainable_reputation(runtime_dir)
    rep_contrib = {c: rep.get(c, {}) for c in chans[:8]}
    if policy_matches is None:
        policy_matches, _, _ = evaluate_policies(
            posts,
            runtime_dir=runtime_dir,
            topic_key=topic_hint,
            dominant_channel=dom,
            fingerprint=fingerprint,
        )
    trace_dict = ranking_trace.to_dict() if hasattr(ranking_trace, "to_dict") else dict(ranking_trace or {})
    div = diversity_metrics(runtime_dir)
    reasons = list(selection_reasons or [])
    reasons.extend(trace_dict.get("reason_codes") or [])
    if pipeline_decision:
        reasons.extend(pipeline_decision.get("suppression_reasons") or [])
    return {
        "selection_reasons": list(dict.fromkeys(reasons))[:32],
        "ranking_score_breakdown": trace_dict,
        "policy_matches": list(policy_matches or [])[:24],
        "suppression_bypasses": list(suppression_bypasses or []),
        "source_reputation_contribution": rep_contrib,
        "diversity_contribution": {
            "topic_distribution": div.get("topic_distribution"),
            "source_distribution": div.get("source_distribution"),
        },
        "pipeline_decision_summary": {
            "suppress": bool((pipeline_decision or {}).get("suppress")),
            "defer": bool((pipeline_decision or {}).get("defer_to_next_tick")),
            "hold": bool((pipeline_decision or {}).get("hold_for_review")),
        },
    }
