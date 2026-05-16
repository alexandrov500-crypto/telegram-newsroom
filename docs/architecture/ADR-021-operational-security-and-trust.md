# ADR-021: Operational security and trust (opt-in)

Status: **Accepted**  
Date: 2026-05-15

## Context

Mature operations require secrets hygiene and trust documentation without becoming an enterprise security platform.

## Decision

- Add `docs/security/*`, security runbooks, opt-in `SECURITY_REDACTION` + `utils/security_redaction.py`
- Read-only `dependency_audit`, `security_posture_check`, `security_readiness` tools
- Supplemental `utils/artifact_integrity.py` — does not alter frozen runtime JSON
- Default: redaction **off** for backward compatibility

## Consequences

- **Positive:** Safer logs when enabled; clear trust boundaries
- **Negative:** Maintainers must extend redaction patterns as needed
- **Negative:** Redaction not a substitute for secret rotation

## Non-goals

- Vault/KMS, SOC2, K8s policy engines, mandatory SIEM

## Related

- [secrets_hygiene.md](../security/secrets_hygiene.md) · [v1_6_security_hardening_report.md](../v1_6_security_hardening_report.md)
