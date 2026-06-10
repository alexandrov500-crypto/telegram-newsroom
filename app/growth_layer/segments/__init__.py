"""Segment-aware growth intelligence."""

from app.growth_layer.segments.content_segments import ALL_SEGMENTS, ContentSegment, classify_content_segment
from app.growth_layer.segments.routing import get_recommended_mode_for_segment, persist_segment_decisions_snapshot
from app.growth_layer.segments.segment_decision import build_segment_decision_map, evaluate_segment_strategy
from app.growth_layer.segments.segment_statistics import build_segment_performance

__all__ = [
    "ContentSegment",
    "ALL_SEGMENTS",
    "classify_content_segment",
    "build_segment_performance",
    "evaluate_segment_strategy",
    "build_segment_decision_map",
    "get_recommended_mode_for_segment",
    "persist_segment_decisions_snapshot",
]
