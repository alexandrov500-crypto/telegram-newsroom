# Governance Tuning Proposal — `GOV-TUN-20260603-D358F7`

> **SUGGESTION ONLY — NO AUTO-APPLY.** Route approved changes through evolution pipeline.

**Health score:** 57.0 · **Trend:** degrading

## Drift status

- Detected: **True**
- Type: `multi_drift:verifier_rule_erosion,adversarial_coverage_degradation,gate_instability`
- Severity: **CRITICAL**

## Recommended tuning (human review)

- **verifier_rule_update** [tighten] `github/adversarial_verifier_patterns.yaml`: Expand verifier patterns from adversarial reports — coverage degraded
- **drift_remediation** [review_only] `evolution_pipeline`: Expand adversarial_verifier_patterns from latest red-team reports

## Overfitting risk

Level: **LOW**

---
_Human approval required · evolution pipeline · Risk Auditor final authority._
