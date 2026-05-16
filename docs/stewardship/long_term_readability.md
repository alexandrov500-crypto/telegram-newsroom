# Long-term readability audit

Periodic readability review — not a one-time pass score.

## Doc discoverability

| Entry | Role | Status |
|-------|------|--------|
| START_HERE.md | Hub | Primary |
| ARCHITECTURE_MAP.md | Flows | Supporting |
| architecture/README.md | ADR index | SSOT |
| docs/stewardship/ | History | This phase |
| Makefile docs-map | CLI index | Run `make docs-map` |

**Risk:** Too many phase reports without START_HERE links — mitigated by CHANGELOG + START_HERE updates each phase.

## Onboarding clarity

Recommended path for 2030 maintainer:

1. START_HERE → ENGINEERING_PHILOSOPHY
2. adr_lineage_map.md (why world looks this way)
3. release_archaeology.md (timeline)
4. RUNTIME_CONTRACTS.md (frozen rules)
5. `make demo-runtime`

## Operational readability

- Runbooks: action-oriented headers (Detection, Mitigation)
- Semantics: tables with violation symptoms
- Avoid duplicating full matrices in runbooks — link to semantics/

## Terminology drift risks

| Term | Canonical meaning | Stale usage risk |
|------|-------------------|------------------|
| production-lite | Single-node, inspection-first | “prod K8s cluster” |
| OUTPUT_DIR | Inspection output root | Confused with RUNTIME_DIR |
| frozen | Contract must not change casually | “frozen feature” |
| v2 | Major version program | “v2 branch name” |
| advisory | No auto-action | “guaranteed forecast” |

**Mitigation:** Use phase tags in reports (`v1.8`, `v2.x`); link glossary in ENGINEERING_PHILOSOPHY.

## Duplicate governance concepts

| Concept | SSOT |
|---------|------|
| Compatibility | compatibility_policy.md |
| Flags | feature_flag_governance.md |
| Scale limits | scalability/operational_topologies.md |
| Invariants | semantics/operational_invariants.md |
| v2 gates | architecture/v2_transition_strategy.md |
| History | stewardship/ (this dir) |

Do not add parallel “policy.md” without superseding ADR.

## Hidden assumptions

Surfaced in:

- semantics/assumption_audit.md
- stewardship/operational_history.md
- architecture/future_scalability_realities.md

## Readability maintenance

- Quarterly: run `history_guardrails.py`
- Each phase: one START_HERE bullet, one CHANGELOG section
- Reject docs that repeat entire matrices — link instead
