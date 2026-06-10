"""Production Editorial Stability & Growth Layer."""

from app.editorial.stability.anti_pause import AntiPauseStatus, evaluate_anti_pause, record_silence_event
from app.editorial.stability.config import stability_layer_enabled
from app.editorial.stability.controller import (
    content_hash_for_text,
    enrich_draft_for_stability,
    evaluate_stability_context,
    merge_stability_extras_json,
    note_stability_publish,
    sources_payload_for_synthesis,
)
from app.editorial.stability.elastic_fill import (
    build_context_post_from_buffer,
    pick_elastic_cluster,
    record_cluster_buffer,
)
from app.editorial.stability.growth_decision import GrowthDecision, evaluate_growth_decision
from app.editorial.stability.mode_controller import (
    PublishingMode,
    StabilityContext,
    primary_governance_suppress_reason,
    should_bypass_governance,
)
from app.editorial.stability.packaging import apply_editorial_packaging, infer_rubric_tag
from app.editorial.stability.slo import record_stability_publish, stability_slo_snapshot
from app.editorial.stability.synthesis import build_synthesis_post, mark_synthesis_emitted

__all__ = [
    "AntiPauseStatus",
    "GrowthDecision",
    "PublishingMode",
    "StabilityContext",
    "apply_editorial_packaging",
    "build_context_post_from_buffer",
    "build_synthesis_post",
    "content_hash_for_text",
    "enrich_draft_for_stability",
    "evaluate_anti_pause",
    "evaluate_growth_decision",
    "evaluate_stability_context",
    "infer_rubric_tag",
    "mark_synthesis_emitted",
    "merge_stability_extras_json",
    "note_stability_publish",
    "pick_elastic_cluster",
    "primary_governance_suppress_reason",
    "record_cluster_buffer",
    "record_silence_event",
    "record_stability_publish",
    "should_bypass_governance",
    "sources_payload_for_synthesis",
    "stability_layer_enabled",
    "stability_slo_snapshot",
]
