# ADR-013: Runtime policy and guardrail semantics

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_policy.py`, `runtime/runtime_policy.json`, `runtime/policy_report.json`, `newsroom.cli inspect-policy`.

## Context

Capability profiles and drift checks capture **what the runtime assumes**. Operators also need an explicit **policy document** for architectural guardrails (bounded history, latest-only artifacts, no distributed coordination) — without a policy engine, admission controller, or governance platform.

## Decision

- Emit **`runtime_policy.json`** with `runtime_policies`, `runtime_guardrails`, and `policy_constraints` aligned to existing constants (`HISTORY_LIMIT`, schema version, duration threshold).
- Emit **`policy_report.json`** from **`validate_runtime_policy`** (FAIL/WARNING/OK).
- Optional lightweight cross-check against on-disk artifacts (history limit, schema versions, capability model).
- CLI: **`inspect-policy [--json] [--strict] [--write]`**; nightly tail writes policy + report after capabilities.
- Validation-only — no enforcement daemon, no runtime mutation.

**Runtime policies are operational inspection artifacts, not enforcement systems.**

## Consequences

- **Positive:** Guardrails are machine-readable and grep-friendly for CI/shell gates.
- **Positive:** Constraints stay synchronized with code constants when policy is regenerated.
- **Negative:** Policy does not block misconfiguration at runtime — only reports drift at inspection time.
- **Negative:** Manual edits to policy JSON can disagree with regenerated canonical policy until `--write`.

## Non-goals

- Policy engine, admission controller, enforcement daemon, governance platform.
- Dynamic policy negotiation, distributed policy sync, automatic remediation, infrastructure governance tooling.
