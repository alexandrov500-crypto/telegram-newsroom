# Repository map

Orientation index for engineers. Not a substitute for [START_HERE.md](START_HERE.md) or [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md).

## Top-level directories

| Path | Role |
|------|------|
| `app/` | Application entry (`python -m app.main`), config, health HTTP |
| `collector/` | Telethon channel ingestion |
| `ai/` | OpenAI prompts and calls |
| `bot/` | aiogram admin bot (approve/reject/publish) |
| `db/` | SQLAlchemy models and repositories |
| `scheduler/` | APScheduler pipeline jobs |
| `publisher/` | Publish formatting, rate limits, locks |
| `worker/`, `workers/` | Optional queue workers |
| `observability/` | **Frozen** runtime JSON builders (inspection only) |
| `newsroom/cli/` | Inspection CLI (`health`, `verify-runtime`, `runtime-index`, …) |
| `utils/` | Logging, metrics, `runtime_ops`, bundles, preflight |
| `tools/` | Operator scripts (`runtime_ops.py`, qualification, retention, …) |
| `tests/` | `runtime/`, `smoke/`, `contracts/`, `failure/`, … |
| `docs/` | Operator and architecture documentation |
| `deploy/` | production-lite env, Compose, systemd examples |
| `examples/` | `runtime_samples/`, `demo_outputs/`, `demo_walkthrough/` |
| `scripts/` | CI shell wrappers (`nightly_runtime.sh`, `release_check.sh`) |
| `.github/workflows/` | Bounded pytest workflows |

## Runtime modules (`observability/`)

| Module | Artifact |
|--------|----------|
| `health_snapshot.py` | `health_snapshot.json` |
| `runtime_report.py` | `runtime_report.json` |
| `runtime_manifest.py` | `runtime_manifest.json` |
| `runtime_verify.py` | (verification result; used by CLI) |
| `runtime_recovery.py` | `recovery_report.json` |
| `runtime_schema.py` | `compatibility_report.json` |
| `runtime_history.py` | `qualification_history.json`, `audit_snapshot.json` |
| `runtime_baseline.py` | `runtime_baseline.json`, `drift_report.json` |
| `runtime_capabilities.py` | `runtime_capabilities.json`, `capability_report.json` |
| `runtime_policy.py` | `runtime_policy.json`, `policy_report.json` |
| `runtime_index.py` | `runtime_index.json` |
| `runtime_contracts.py` | Frozen SSOT (not an on-disk artifact) |

## Docs structure

```
docs/
├── START_HERE.md              # Onboarding hub
├── ARCHITECTURE_MAP.md        # ASCII flows
├── REPOSITORY_MAP.md          # This file
├── REPRODUCIBILITY.md
├── REPOSITORY_STANDARDS.md
├── ENGINEERING_PHILOSOPHY.md
├── FAQ.md, CONTRIBUTING.md
├── OPERATOR_QUICKSTART.md
├── DEPLOYMENT_QUICKSTART.md
├── RUNTIME_OPS.md
├── RELEASE_*.md
├── examples/                  # Failure/drift playbooks
└── architecture/              # ADRs, RUNTIME_CONTRACTS
```

## Tests structure

```
tests/
├── runtime/       # tools/utils ops modules
├── smoke/         # Artifact builder integration
├── contracts/     # Frozen layout, docs, Makefile stability
├── failure/       # Failure injection scenarios
├── recovery/      # Recovery cadence
└── …              # Domain unit tests
```

## Deploy and examples

```
deploy/
├── example.env.production-lite
├── docker-compose.production-lite.yml
└── systemd/newsroom-nightly.*

examples/
├── runtime_samples/     # Sanitized JSON
├── demo_outputs/        # CLI transcripts
└── demo_walkthrough/    # Dry-run shell scripts
```

## Makefile entrypoints

| Target | Purpose |
|--------|---------|
| `make quality` | contracts + smoke + lint + format-check |
| `make ci-test` | runtime + smoke + contracts (CI) |
| `make runtime-help` | Inspection command groups |
| `make docs-map` | Doc index |

## Related

- [REPOSITORY_STANDARDS.md](REPOSITORY_STANDARDS.md)
- [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
