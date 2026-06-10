"""Growth Layer editorial intelligence."""

from app.growth_layer.editorial.api import get_segment_editorial_recommendations
from app.growth_layer.editorial.editorial_recommendations import generate_editorial_recommendations
from app.growth_layer.editorial.feature_extraction import extract_editorial_features
from app.growth_layer.editorial.pattern_discovery import discover_growth_patterns
from app.growth_layer.editorial.scorecard import evaluate_post_editorial_score
from app.growth_layer.editorial.snapshot import persist_editorial_intelligence_snapshot

__all__ = [
    "extract_editorial_features",
    "discover_growth_patterns",
    "generate_editorial_recommendations",
    "evaluate_post_editorial_score",
    "get_segment_editorial_recommendations",
    "persist_editorial_intelligence_snapshot",
]
