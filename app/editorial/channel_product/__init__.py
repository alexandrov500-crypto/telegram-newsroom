"""Channel as Product — Telegram-native growth loop + viral mechanics."""

from app.editorial.channel_product.acquisition_attribution import build_acquisition_attribution
from app.editorial.channel_product.config import channel_product_enabled
from app.editorial.channel_product.controller import enrich_draft_with_channel_product
from app.editorial.channel_product.cta_optimizer import select_cta_variant
from app.editorial.channel_product.feedback_bridge import topic_weights_from_feedback
from app.editorial.channel_product.growth_loop import GrowthLoopStage, classify_growth_loop
from app.editorial.channel_product.kpi import channel_product_kpi_snapshot
from app.editorial.channel_product.render_bridge import channel_product_from_extras, merged_growth_meta_from_extras
from app.editorial.channel_product.state import channel_product_snapshot, record_channel_product_event
from app.editorial.channel_product.viral_mechanics import evaluate_viral_mechanics

__all__ = [
    "GrowthLoopStage",
    "build_acquisition_attribution",
    "channel_product_enabled",
    "channel_product_from_extras",
    "channel_product_kpi_snapshot",
    "channel_product_snapshot",
    "classify_growth_loop",
    "enrich_draft_with_channel_product",
    "evaluate_viral_mechanics",
    "merged_growth_meta_from_extras",
    "record_channel_product_event",
    "select_cta_variant",
    "topic_weights_from_feedback",
]
