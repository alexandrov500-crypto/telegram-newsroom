# v2.x legacy stewardship report

Controlled legacy aging and sunset readiness — documentation and read-only tooling only.

## Legacy Stewardship Grade

| Area | Grade | Notes |
|------|-------|-------|
| Legacy state clarity | A | legacy_state_definition.md |
| Sunset scenarios | A | controlled_sunset.md |
| Recoverability honesty | A | recoverability_guarantees.md |
| Anti-pattern guard | A | legacy_antipatterns.md |
| Operational envelope | A | T1/T3 legacy focus |

**Overall:** Ready for long-term legacy stewardship without abandonment or perpetual evolution.

## Controlled Sunset Confidence

Scenarios documented: slow dev, maintenance-only, multi-year silence, handoff, drift, final stewardship.

**Confidence:** High for tag+archive path; medium for untested `main` on future Python.

## Long-Term Recoverability Status

Level **A** achievable: tag + sqlite + OUTPUT_DIR + docs → validate-recovery.

See [recoverability_guarantees.md](legacy/recoverability_guarantees.md).

## Dormant-State Survivability

[ecosystem_continuity.md](stewardship/ecosystem_continuity.md) + [stewardship_sunset_governance.md](legacy/stewardship_sunset_governance.md):

- Passive quarterly/annual cadence
- No governance inflation
- Opt-in flags re-enabled deliberately

## Remaining Ecosystem Risks

| Risk | Legacy response |
|------|-----------------|
| Telegram/OpenAI drift | Pin + uplift; not guaranteed |
| Maintainer absence | ADR + tag archive |
| False HA deploy | unsupported_deployments |
| Rewrite pressure | legacy_antipatterns |

## Recommended Final Stewardship Posture

**Final posture (recommended):**

1. Declare last **stable legacy tag** when entering maintenance-only
2. Passive cadence: `legacy-validate` + `preservation-validate` quarterly
3. Annual recovery drill
4. No new guardrails tools; no default-on flags
5. v2 only via explicit gates — never “sunset rewrite”

Not required: shutdown automation, archive-only repo, enterprise lifecycle program.

## Legacy Survivability Assessment

Legacy = frozen contracts + operable T1/T3 + documented recovery — supported without active feature work.

## Controlled Sunset Readiness

Sunset paths are **controlled** (operator-driven), not automated decommission.

## Long-Term Recoverability Confidence

Documented confidence levels A–D; target A for disciplined operators.

## Stewardship Scale-Down Readiness

Scale-down ladder in stewardship_sunset_governance.md; simplification rules prevent governance sprawl.

## Remaining Long-Horizon Risks

External APIs and Python EOL — same as preservation phase; no new runtime mitigations (by design).

## Recommended Legacy Stewardship Model

| Stage | Actions |
|-------|---------|
| Entering legacy | Tag + validation reports |
| Passive | Quarterly legacy/preservation validate |
| Dormant | Tag-only install; external archive |
| Handoff | adr_lineage + controlled_sunset checklist |

## Validation

```bash
make legacy-validate
make ci-test
make governance-validate
make architecture-validate
```

## Backward compatibility

- No runtime changes
- No governance process rewrite
- Compatible with preservation/traceability phases
