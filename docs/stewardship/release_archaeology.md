# Release archaeology

How the production-lite line evolved after v1.0.0 — motivation, constraints, rejected paths.

## v1.0 freeze origin

| Field | Detail |
|-------|--------|
| **Motivation** | Ship inspectable, governable newsroom ops without platform team |
| **Constraints** | 14 runtime artifacts, 11 CLIs, schema v1 |
| **Tradeoff** | Less flexibility vs operator predictability |
| **Rejected** | Open-ended governance modules, mandatory K8s |
| **Evidence** | ADR-015–017, `STABILITY_GUARANTEES.md` |

## Post-v1 hardening path

| Field | Detail |
|-------|--------|
| **Motivation** | Close reliability gaps without breaking freeze |
| **Constraints** | Opt-in flags default off |
| **Tradeoff** | More env surface vs backward compatibility |
| **Rejected** | Default-on behavior changes |
| **Artifacts** | `post_v1_hardening.md`, ADR-019, RFC backlog |

## Chaos / resilience (v1.1 → v1.3)

| Field | Detail |
|-------|--------|
| **Motivation** | Prove retry/lock/recovery under failure |
| **Constraints** | CI-safe chaos/soak; no prod auto-inject |
| **Tradeoff** | Test + doc burden vs silent data loss |
| **Rejected** | Distributed chaos platform |
| **Artifacts** | `v1_1_operational_validation_report.md`, `v1_3_*`, `tests/chaos/`, `tests/soak/` |

## Governance (v1.4)

| Field | Detail |
|-------|--------|
| **Motivation** | Safe PATCH/MINOR and flag discipline |
| **Constraints** | Readiness tools, no new frozen artifacts |
| **Rejected** | Mandatory external release SaaS |
| **Artifacts** | `compatibility_policy.md`, `release_readiness.py` |

## Security (v1.6)

| Field | Detail |
|-------|--------|
| **Motivation** | Trust boundaries, redaction, supply chain awareness |
| **Constraints** | `SECURITY_REDACTION=1` opt-in |
| **Rejected** | Mandatory Vault / SIEM |
| **Artifacts** | `docs/security/*`, `v1_6_security_hardening_report.md` |

## Scalability boundaries (v1.8)

| Field | Detail |
|-------|--------|
| **Motivation** | Honest scale limits; prevent platform creep |
| **Constraints** | Docs + diagnostics only |
| **Rejected** | Postgres/K8s as “fix” |
| **Artifacts** | `docs/scalability/*`, scaling runbooks |

## Semantics formalization (v2.x)

| Field | Detail |
|-------|--------|
| **Motivation** | Explicit invariants and forbidden states |
| **Constraints** | No runtime rewrite |
| **Rejected** | Theorem provers, model checking |
| **Artifacts** | `docs/semantics/*`, `semantics_guardrails.py` |

## Stewardship & traceability (v2.x)

| Field | Detail |
|-------|--------|
| **Motivation** | Long-term comprehension after maintainer churn |
| **Constraints** | Docs + read-only guardrails |
| **Rejected** | Git rewrite, compliance archive |
| **Artifacts** | `docs/stewardship/*`, this file |

## Tagging convention (informal)

- **1.0.x** — contract-compatible maintenance
- **Unreleased CHANGELOG** — stewardship phases documented before tag
- **Reports** — `v1_N_*_report.md` validation snapshots, not SLAs
