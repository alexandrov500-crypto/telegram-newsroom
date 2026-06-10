"""AUH orchestration — post-processing after EGDL."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.audience_unification.auh_transformer import transform_for_unified_audience
from app.editorial.audience_unification.communication_balance import evaluate_communication_balance
from app.editorial.audience_unification.config import auh_enabled
from app.editorial.audience_unification.cross_replacement_score import compute_crs
from app.editorial.audience_unification.reader_simulator import evaluate_reader_profile
from app.editorial.audience_unification.state import record_auh_evaluation
from app.editorial.audience_unification.unified_editorial_score import compute_ues
from app.editorial.audience_unification.unified_packaging import apply_unified_packaging
from app.editorial.audience_unification.universal_value_filter import evaluate_universal_value
from app.editorial.stability.anti_pause import evaluate_anti_pause


@dataclass(frozen=True)
class AUHEvaluation:
    reject: bool
    force_digest: bool
    publish_immediately: bool
    priority_boost: bool
    body: str
    extras: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reject": self.reject,
            "force_digest": self.force_digest,
            "publish_immediately": self.publish_immediately,
            "priority_boost": self.priority_boost,
        }


def _extract_gravity(dom_extras: dict[str, Any]) -> tuple[float, bool, float]:
    dom = dom_extras.get("editorial_dominance") if isinstance(dom_extras.get("editorial_dominance"), dict) else {}
    grav = dom.get("gravity") if isinstance(dom.get("gravity"), dict) else {}
    sg = dom.get("source_graph") if isinstance(dom.get("source_graph"), dict) else {}
    att = dom.get("attention_design") if isinstance(dom.get("attention_design"), dict) else {}
    return (
        float(grav.get("total") or 50.0),
        bool(att.get("has_implication")),
        float(sg.get("independence_score") or 0.75),
    )


def enrich_draft_with_auh(
    body: str,
    *,
    runtime_dir: str | None,
    editorial_category: str,
    quality_score: float,
    publishing_mode: str,
    cluster_size: int = 1,
    newsroom_tz: str = "Europe/Moscow",
    dom_extras: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    if not auh_enabled():
        return body, {}

    dom_extras = dom_extras or {}
    gravity_total, has_implication, source_indep = _extract_gravity(dom_extras)

    reader = evaluate_reader_profile(body)
    transformed, transform_meta = transform_for_unified_audience(
        body,
        matched_interests=reader.matched_interests,
        editorial_category=editorial_category,
    )
    reader = evaluate_reader_profile(transformed)

    uvf = evaluate_universal_value(
        transformed,
        cross_interest_breadth=reader.cross_interest_breadth,
        cluster_size=cluster_size,
        publishing_mode=publishing_mode,
    )

    balance = evaluate_communication_balance(transformed)
    crs = compute_crs(
        transformed,
        cross_interest_breadth=reader.cross_interest_breadth,
        reader_clarity=reader.gender_neutral_clarity_score,
        quality_score=quality_score,
        has_implication=has_implication,
        cluster_size=cluster_size,
    )

    ues = compute_ues(
        gravity_total=gravity_total,
        crs_total=crs.total,
        reader_relevance=reader.reader_relevance_score,
        clarity=balance.clarity_index,
        source_independence=source_indep,
        crs_flagship=crs.flagship,
        publishing_mode=publishing_mode,
    )

    packaged, pkg_meta = apply_unified_packaging(
        transformed,
        flagship=ues.flagship or crs.flagship,
    )

    record_auh_evaluation(
        runtime_dir,
        ues=ues.total,
        crs=crs.total,
        reader_relevance=reader.reader_relevance_score,
        published=False,
    )

    reject = ues.reject or (not uvf.passes and publishing_mode == "core")
    force_digest = ues.force_digest or uvf.downgrade_to_digest
    priority = ues.publish_immediately or ues.flagship

    ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
    if reject and (ap.anti_pause_active or publishing_mode != "core"):
        reject = False
        force_digest = True

    extras: dict[str, Any] = {
        "audience_unification": {
            "reader_simulation": reader.to_dict(),
            "transform": transform_meta,
            "universal_value_filter": uvf.to_dict(),
            "communication_balance": balance.to_dict(),
            "crs": crs.to_dict(),
            "ues": ues.to_dict(),
            "unified_packaging": pkg_meta,
            "objective": "maximize_cross_source_cognitive_replacement_per_user",
        }
    }
    if reject:
        extras["auh_reject"] = True
    if force_digest:
        extras["force_digest_slot"] = True
    if priority:
        extras["priority_boost"] = True
    if ues.flagship or crs.flagship:
        extras["flagship_post"] = True

    return packaged, extras


def compress_cluster_for_auh(
    texts: list[str],
    *,
    topic_hint: str = "",
) -> tuple[str, dict[str, Any]]:
    from app.editorial.audience_unification.audience_compression_engine import compress_cluster_narrative

    return compress_cluster_narrative(texts, topic_hint=topic_hint)
