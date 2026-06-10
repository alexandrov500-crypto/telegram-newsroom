"""Global Multi-Channel Competitive Simulation Layer."""

from app.editorial.gmcs.controller import run_gmcs_competitive_analysis
from app.editorial.gmcs.state import gmcs_snapshot, record_gmcs_evaluation

__all__ = ["gmcs_snapshot", "record_gmcs_evaluation", "run_gmcs_competitive_analysis"]
