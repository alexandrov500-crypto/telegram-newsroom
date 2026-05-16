# Support

## What to expect

This is a **stable v1.0.0** production-lite system. Support means:

- Bug fixes compatible with frozen runtime contracts
- Documentation and reproducibility improvements
- Clarifications on operator workflows (`make runtime-help`, [docs/START_HERE.md](docs/START_HERE.md))

## Issue guidelines

**Good issues:** reproducible bugs, doc errors, contract test failures, unclear operator steps.

**Likely declined:** requests for new runtime governance artifacts, orchestration engines, Kubernetes manifests, Prometheus/Grafana integration, web admin UI, deployment automation bots.

## Non-goals

See [docs/FAQ.md](docs/FAQ.md) and [docs/architecture/RUNTIME_MATURITY.md](docs/architecture/RUNTIME_MATURITY.md). The project intentionally avoids platform-scale complexity.

## Maintenance philosophy

- **Compatibility-first** — additive changes preferred ([docs/MAINTENANCE_POLICY.md](docs/MAINTENANCE_POLICY.md)).
- **New architectural layers require exceptional justification.**
- Release discipline over deployment automation ([docs/RELEASE_PROCESS.md](docs/RELEASE_PROCESS.md)).

## Production-lite expectations

- Single-node deployment; you operate backups, `.env`, and systemd/Compose.
- Runtime inspection is **offline** and **manual** — no SaaS control plane included.
- Optional Redis/Postgres paths are documented but not mandatory.

Before tagging a release locally: `make release-check`.
