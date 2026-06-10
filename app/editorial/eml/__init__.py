"""Editorial Monetization Layer — attention → value → revenue."""

from app.editorial.eml.controller import enrich_with_editorial_monetization
from app.editorial.eml.state import eml_snapshot, record_eml_evaluation

__all__ = ["eml_snapshot", "enrich_with_editorial_monetization", "record_eml_evaluation"]
