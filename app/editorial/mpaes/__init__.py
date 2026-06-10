"""Multi-Persona Adaptive Editorial System — hub channel for male + female readers."""

from app.editorial.mpaes.controller import (
    apply_mpaes_to_decision,
    enrich_draft_with_mpaes,
    evaluate_mpaes_state,
)
from app.editorial.mpaes.persona_registry import DemographicSegment, PersonaProfile, all_hub_personas
from app.editorial.mpaes.state import mpaes_snapshot, record_mpaes_evaluation

__all__ = [
    "DemographicSegment",
    "PersonaProfile",
    "all_hub_personas",
    "apply_mpaes_to_decision",
    "enrich_draft_with_mpaes",
    "evaluate_mpaes_state",
    "mpaes_snapshot",
    "record_mpaes_evaluation",
]
