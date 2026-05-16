# v1.6 security hardening report

**Branch:** `v1.6-security-hardening`  
**Scope:** Opt-in redaction, read-only security tooling, documentation — no frozen contract changes

---

## Security posture assessment

**Grade: B+ → A- (production-lite with discipline)**

Improvements: deterministic redaction (`SECURITY_REDACTION=1`), posture checker, dependency audit, supplemental integrity catalog, security runbooks. Not a zero-trust platform.

---

## Trust boundary assessment

Documented in [security/trust_boundaries.md](security/trust_boundaries.md): trusted inspection surface vs untrusted restored evidence vs external APIs.

---

## Secrets hygiene status

| Area | Status |
|------|--------|
| Env / `.env` | Documented; operator-owned |
| Logs | Opt-in redaction |
| DLQ tracebacks | Opt-in redaction |
| Evidence JSON | No tokens by design; operator discipline |
| Backups | Confidential |

---

## Artifact integrity status

- Frozen `verify-runtime` unchanged
- Supplemental `utils/artifact_integrity.py` for operator-side catalogs
- Tamper runbook linked

---

## Auditability assessment

- `correlation_id`, `tick_id`, `event_id`, `delivery_id` chain documented
- Bounded log/event buffers unchanged

---

## Unsafe configuration risks

Detected by `tools/security_posture_check.py`:

- Strict lock without Redis
- Legacy retry under Redis
- DEBUG logging
- World-writable OUTPUT_DIR
- Redaction disabled

---

## Supply chain risk assessment

- `tools/dependency_audit.py` — pin policy + forbidden list
- Ranges allowed only for documented packages
- CVE response per DEPENDENCY_POLICY

---

## Remaining security risks

- Redaction off by default (backward compatibility)
- No HSM/Vault integration
- Single-node trust model
- Operator may skip backup/rotation
- CI placeholders not production secrets but still rotate if leaked

---

## Recommended v1.7 priorities

1. Enable `SECURITY_REDACTION=1` in production-lite env template comments
2. CI job: `security-readiness --strict` on security path changes
3. Optional `integrity-report` Makefile target
4. Extend redaction patterns from incident feedback only
5. Signed tags documentation (optional, no in-repo crypto)

---

## Validation

```bash
make ci-test
make release-check
make governance-validate
make resilience-validate
make security-validate
python3 tools/security_readiness.py --strict
```
