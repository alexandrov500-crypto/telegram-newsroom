"""High-trust publish mode — stricter auto-publish rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import Settings
from app.editorial.scoring_engine import EditorialScore, score_story
from app.editorial.source_tiers import aggregate_source_tier
from app.editorial.tone_engine import apply_newsroom_tone
from app.editorial.trust_system import evaluate_editorial_trust


@dataclass(frozen=True)
class TrustModeVerdict:
    allowed: bool
    manual_review_required: bool
    permanent_block: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "manual_review_required": self.manual_review_required,
            "permanent_block": self.permanent_block,
            "reason": self.reason,
        }


def newsroom_trust_mode(settings: Settings | None = None) -> str:
    if settings is not None:
        return str(getattr(settings, "newsroom_trust_mode", "off") or "off").strip().lower()
    import os

    return os.getenv("NEWSROOM_TRUST_MODE", "off").strip().lower()


def is_high_trust_mode(settings: Settings | None = None) -> bool:
    return newsroom_trust_mode(settings) in {"high", "strict", "maximum"}


def evaluate_trust_mode(
    text: str,
    *,
    sources: list[str] | None = None,
    runtime_dir: str | None = None,
    settings: Settings | None = None,
    operator_approved: bool = False,
) -> TrustModeVerdict:
    """
    When NEWSROOM_TRUST_MODE=high:
    - controversial → manual
    - rumor → block
    - contradiction → block
    - single-source tier3 → manual
    - sensational tone → reject
    """
    if not is_high_trust_mode(settings):
        return TrustModeVerdict(True, False, False, "trust_mode_off")

    chans = list(sources or [])
    unique = len({s.strip().lower() for s in chans if s.strip()})
    tier = aggregate_source_tier(chans, runtime_dir=runtime_dir)
    escore = score_story(text=text, sources=chans, runtime_dir=runtime_dir)
    trust = evaluate_editorial_trust(text, escore, sources=chans, runtime_dir=runtime_dir)

    tone = apply_newsroom_tone(text)
    if not tone.is_acceptable:
        return TrustModeVerdict(False, False, True, "trust_mode_sensational_reject")

    if trust.rumor_risk >= 0.55:
        return TrustModeVerdict(False, False, True, "trust_mode_rumor_block")

    if trust.source_contradiction:
        return TrustModeVerdict(False, False, True, "trust_mode_contradiction_block")

    if trust.controversial_escalation and not operator_approved:
        return TrustModeVerdict(False, True, False, "trust_mode_controversial_manual")

    if tier.tier >= 3 and unique < 2 and not operator_approved:
        return TrustModeVerdict(False, True, False, "trust_mode_tier3_single_source_manual")

    return TrustModeVerdict(True, False, False, "trust_mode_ok")
