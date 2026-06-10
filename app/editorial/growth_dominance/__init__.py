"""Editorial Growth Dominance Layer (EGDL)."""

from app.editorial.growth_dominance.arbitration import ArbitrationDecision, arbitrate_stability_vs_growth
from app.editorial.growth_dominance.attention_design import evaluate_attention_design
from app.editorial.growth_dominance.config import egdl_enabled
from app.editorial.growth_dominance.controller import (
    DominanceEvaluation,
    enrich_draft_with_dominance,
    evaluate_content_dominance,
)
from app.editorial.growth_dominance.dominance_loops import DominanceLoop, classify_dominance_loop
from app.editorial.growth_dominance.gravity import GravityBreakdown, compute_gravity_score
from app.editorial.growth_dominance.hashtag_engine import apply_growth_hashtags, infer_growth_hashtag
from app.editorial.growth_dominance.kpi import egdl_kpi_snapshot
from app.editorial.growth_dominance.source_graph import SourceGraphEvaluation, evaluate_cluster_source_graph

__all__ = [
    "ArbitrationDecision",
    "DominanceEvaluation",
    "DominanceLoop",
    "GravityBreakdown",
    "SourceGraphEvaluation",
    "apply_growth_hashtags",
    "arbitrate_stability_vs_growth",
    "classify_dominance_loop",
    "compute_gravity_score",
    "egdl_enabled",
    "egdl_kpi_snapshot",
    "enrich_draft_with_dominance",
    "evaluate_attention_design",
    "evaluate_cluster_source_graph",
    "evaluate_content_dominance",
    "infer_growth_hashtag",
]
