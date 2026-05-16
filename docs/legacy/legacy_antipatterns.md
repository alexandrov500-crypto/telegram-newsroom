# Legacy anti-patterns

Forbidden responses to dormancy or sunset pressure.

## Rewrite-before-sunset

**Anti-pattern:** “We’ll rewrite v2 before we maintain v1.”

**Why forbidden:** Loses recovery evidence; violates [v2_transition_strategy.md](../architecture/v2_transition_strategy.md) gates.

**Instead:** Tag stable legacy; passive stewardship.

## Panic modernization

**Anti-pattern:** Upgrade all dependencies because the project feels old.

**Why forbidden:** Breaks tag recoverability; no measured pain.

**Instead:** CVE-only or EOL-driven uplift ([dependency_preservation.md](../preservation/dependency_preservation.md)).

## Dependency churn before dormancy

**Anti-pattern:** Merge sweeping pin updates then go dormant.

**Why forbidden:** Last known-good tag lost.

**Instead:** Tag first, then minimal pins if needed.

## Governance inflation during low activity

**Anti-pattern:** New committees, new policy docs, new mandatory gates each quarter.

**Why forbidden:** Stewardship overhead exceeds value ([complexity_budget.md](../architecture/complexity_budget.md)).

**Instead:** Reuse existing validate targets; doc clarifications only.

## Speculative rescue rewrites

**Anti-pattern:** Microservices/Postgres/K8s to “save” a quiet project.

**Why forbidden:** T4 unsupported; increases decay risk.

**Instead:** T1 legacy envelope + archive.

## Hyperscale migration fantasies

**Anti-pattern:** Planning sharding/HA for editorial cadence that fits one node.

**Why forbidden:** [unsupported_deployments.md](../scalability/unsupported_deployments.md).

**Instead:** Document limits; stay production-lite.

## Preservation overengineering

**Anti-pattern:** Vendoring PyPI, offline mirrors, reproducible-build empire.

**Why forbidden:** ADR-027 non-goals.

**Instead:** Tag + sqlite + OUTPUT_DIR archive.

## Abandonment theater

**Anti-pattern:** Delete tests/docs; leave broken `main`; no recovery path.

**Why forbidden:** Violates legacy supported definition.

**Instead:** [recoverability_guarantees.md](recoverability_guarantees.md) level A target.

## Artificial perpetual evolution

**Anti-pattern:** Mandatory roadmap of features despite maintenance mode.

**Why forbidden:** ADR-018 maintenance-first.

**Instead:** Passive stewardship cadence.
