# FAQ

Short engineering answers. Runtime governance is frozen; these explain boundaries, not apologies.

## Why no Kubernetes?

The editorial pipeline is a **single-writer** asyncio application with offline inspection tooling. K8s adds control-plane complexity without solving the core ops problem (read JSON, verify checksums, run nightly). Operators who need K8s can wrap the same container externally; manifests are intentionally out of repo.

## Why no Prometheus?

Metrics are exported as **bounded JSON snapshots and logs**, not a mandatory time-series stack. Production-lite deployments should stay operable with `journalctl`, `make runtime-index`, and static reports. A metrics backend is an optional external choice.

## Why single-node?

SQLite-first and one `RUNTIME_STATE_DIR` match the actual failure modes we optimize for: disk, credentials, pipeline stalls. Multi-node coordination would require new governance artifacts — excluded after contract freeze.

## Why deterministic JSON?

Stable key order and schema version make **diffs, contract tests, and manifest checksums** reliable. Non-deterministic serialization breaks operator trust and CI comparisons.

## Why latest-only artifacts?

Bounded disk and cognitive load. History lives in qualification history (capped) and external backups — not an unbounded artifact archive in-repo.

## Why no orchestration engine?

`runtime_ops.py` is a **sequential script**, not a DAG platform. Inspection steps are idempotent CLIs; there is no scheduler dependency for validation. See ADR-003.

## Why shell-first tooling?

Shell and Make are universal, grep-friendly, and auditable. Operators can run the same commands in CI, cron, or systemd without learning a proprietary CLI graph.

## Why frozen contracts?

After 14 artifacts and 11 inspection commands, further taxonomy growth hurts more than it helps. ADR-015 freezes names, lifecycle, and enums; changes go through contract tests and explicit ADR revision.

## Why inspection-only policies?

Policies document **assumptions** (single-node, no daemons, bounded history). Enforcement belongs in human release process, not autonomous agents — keeping the system understandable.

## Why no deployment automation in CI?

**Release discipline is preferred over deployment automation.** The repo ships verification and templates; pushing to production stays an explicit operator action.

## Where do I start?

[START_HERE.md](START_HERE.md)
