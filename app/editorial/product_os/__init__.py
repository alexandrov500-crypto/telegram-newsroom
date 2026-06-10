"""Productized Editorial OS — cognitive substitution product layer."""

from app.editorial.product_os.audience_reality_v2 import evaluate_audience_reality_v2
from app.editorial.product_os.channel_substitution_engine import evaluate_channel_substitution
from app.editorial.product_os.config import product_os_enabled
from app.editorial.product_os.content_format import ContentFormat, classify_content_format
from app.editorial.product_os.contextual_cta import select_contextual_cta
from app.editorial.product_os.daily_operating_model import evaluate_daily_slot
from app.editorial.product_os.kpi import product_os_kpi_snapshot
from app.editorial.product_os.peos_controller import enrich_draft_with_product_os
from app.editorial.product_os.product_gravity import PGAction, compute_product_gravity
from app.editorial.product_os.replacement_loop import ReplacementStage, classify_replacement_stage
from app.editorial.product_os.render_bridge import merged_growth_meta_with_product_os
from app.editorial.product_os.source_strategy import evaluate_source_strategy
from app.editorial.product_os.state import product_os_snapshot, record_peos_evaluation
from app.editorial.product_os.telegram_mechanics import build_telegram_mechanics
from app.editorial.product_os.virality_v2 import compute_reference_forward_score

__all__ = [
    "ContentFormat",
    "PGAction",
    "ReplacementStage",
    "classify_content_format",
    "classify_replacement_stage",
    "compute_product_gravity",
    "compute_reference_forward_score",
    "enrich_draft_with_product_os",
    "evaluate_audience_reality_v2",
    "evaluate_channel_substitution",
    "evaluate_daily_slot",
    "evaluate_source_strategy",
    "merged_growth_meta_with_product_os",
    "product_os_enabled",
    "product_os_kpi_snapshot",
    "product_os_snapshot",
    "record_peos_evaluation",
    "select_contextual_cta",
    "build_telegram_mechanics",
]
