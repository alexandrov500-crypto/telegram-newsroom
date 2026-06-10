"""Audience Unification Layer — single feed replacing 10–20 sources."""

from app.editorial.audience_unification.auh_transformer import transform_for_unified_audience
from app.editorial.audience_unification.audience_compression_engine import compress_cluster_narrative
from app.editorial.audience_unification.communication_balance import evaluate_communication_balance
from app.editorial.audience_unification.config import auh_enabled
from app.editorial.audience_unification.controller import AUHEvaluation, compress_cluster_for_auh, enrich_draft_with_auh
from app.editorial.audience_unification.cross_replacement_score import compute_crs
from app.editorial.audience_unification.reader_simulator import UnifiedReaderProfile, evaluate_reader_profile
from app.editorial.audience_unification.kpi import auh_kpi_snapshot
from app.editorial.audience_unification.state import auh_distribution_snapshot, record_auh_evaluation
from app.editorial.audience_unification.unified_editorial_score import compute_ues
from app.editorial.audience_unification.unified_packaging import apply_unified_packaging
from app.editorial.audience_unification.universal_value_filter import evaluate_universal_value

__all__ = [
    "AUHEvaluation",
    "UnifiedReaderProfile",
    "apply_unified_packaging",
    "auh_distribution_snapshot",
    "auh_enabled",
    "auh_kpi_snapshot",
    "compress_cluster_for_auh",
    "compress_cluster_narrative",
    "compute_crs",
    "compute_ues",
    "enrich_draft_with_auh",
    "evaluate_communication_balance",
    "evaluate_reader_profile",
    "evaluate_universal_value",
    "record_auh_evaluation",
    "transform_for_unified_audience",
]
