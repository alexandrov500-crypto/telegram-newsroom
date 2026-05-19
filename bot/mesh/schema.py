from __future__ import annotations

from bot.mesh.types import ConstitutionalPolicyDocument

DEFAULT_CONSTITUTION = ConstitutionalPolicyDocument(
    policy_id="mesh_constitution",
    version=1,
    invariants=[
        "operator_supremacy",
        "no_unaudited_publish",
        "no_policy_self_modify",
        "replay_coherence",
        "bounded_autonomy",
    ],
    max_autonomy_level=2,
    require_operator_for_policy_change=True,
    require_simulation_before_promotion=True,
    explainability_required=True,
    protected_actions=[
        "policy_change",
        "constitutional_amend",
        "production_cognition_mutate",
        "bypass_degradation",
    ],
)

DEFAULT_MESH_CONFIG = {
    "gossip_budget_per_tick": 20,
    "quorum_fraction": 0.51,
    "max_propagation_hops": 3,
    "memory_replication_factor": 2,
    "trust_decay_rate": 0.05,
    "cognitive_storm_threshold": 100,
}
