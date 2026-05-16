# ADR-012: Runtime capability and deployment profile semantics

Status: Accepted  
Date: 2026-05-15

Scope: `observability/runtime_capabilities.py`, `runtime/runtime_capabilities.json`, `runtime/capability_report.json`, `newsroom.cli inspect-capabilities`.

## Context

The newsroom runtime ops stack assumes **single-node**, **production-lite**, shell-first operations with bounded artifacts. That intent is spread across ADRs and docs but not captured in a single **machine-readable capability profile** operators can inspect offline.

## Decision

- Emit **`runtime_capabilities.json`** declaring runtime model, deployment profile, supported/unsupported execution modes, characteristics, and constraints.
- Emit **`capability_report.json`** from **`validate_runtime_capabilities`** (FAIL/WARNING/OK rules).
- Integrate profile + report write at end of `nightly-check`.
- CLI: **`inspect-capabilities [--json] [--strict] [--write]`** — inspection-only, no infra mutation.
- Document supported vs unsupported deployment models explicitly in code constants.

**Capability profiles describe operational assumptions, not infrastructure automation.**

## Consequences

- **Positive:** CI and operators can assert deployment assumptions match production-lite single-node model.
- **Positive:** Unsupported models (Kubernetes, distributed workers) are explicit in profile JSON.
- **Negative:** Profile does not probe host/cloud APIs — mismatches with real deployment are possible if operators override files manually.
- **Negative:** Capability refresh is manual/latest-only via nightly or `--write`.

## Non-goals

- Deployment orchestrator, Kubernetes layer, Terraform/Ansible, infrastructure provisioning.
- Distributed coordination, autoscaling, discovery agents, remote capability registry, dynamic negotiation.
