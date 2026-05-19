from __future__ import annotations

from bot.epistemic.types import EpistemicGovernanceDocument

DEFAULT_EPISTEMIC_GOVERNANCE = EpistemicGovernanceDocument(
    policy_id="epistemic_integrity",
    version=1,
    invariants=[
        "truth_integrity",
        "uncertainty_disclosure",
        "minority_preservation",
        "reversible_trust",
        "no_silent_consensus_erasure",
        "operator_supremacy",
    ],
    max_confidence_without_evidence=0.75,
    require_uncertainty_disclosure=True,
    preserve_contradictions=True,
    anti_overconfidence_cap=0.95,
    anti_manipulation_rules=[
        "detect_coordinated_amplification",
        "flag_low_source_diversity",
        "quarantine_on_replay_divergence",
    ],
)

CONFIDENCE_DECAY_RATE = 0.02
MAX_CONFIDENCE_AMPLIFICATION = 0.15
