# Architecture map

ASCII-only topology for runtime, inspection, validation, release, and deployment. Governance model is **frozen** (ADR-015); no new `runtime/*.json` types.

## Governance freeze status

| Area | Status |
|------|--------|
| Runtime artifacts (14 JSON) | Frozen lifecycle order 1–14 |
| Categories / tri-state enums | Frozen in `runtime_contracts.py` |
| Inspection CLIs (11 commands) | Frozen registry |
| New governance layers | **Not planned** |
| Deployment topology | production-lite single-node only |

## Runtime flow (live + nightly ops)

```
┌─────────────────┐     ┌──────────────────┐
│  app.main       │     │ tools/runtime_ops│
│  scheduler+bot  │     │ nightly-check    │
│  RUNTIME_STATE  │     │ sequential steps │
└────────┬────────┘     └────────┬─────────┘
         │                       │
         v                       v
   var/runtime/            OUTPUT_DIR/
   (live JSON state)       runtime/*.json
                           qualification.json
                           runtime_bundle.zip
```

Nightly step order (simplified): preflight → benchmark → soak → bundle → regression → qualification → dashboard → retention → **governance artifacts** → `runtime_index.json` last.

## Inspection flow

```
Operator
   │
   ├─ make runtime-help
   ├─ make runtime-index  ──► runtime_index.json (catalog)
   ├─ make runtime-health ──► health_snapshot.json
   ├─ make verify-runtime ──► manifest checksums
   ├─ make validate-recovery
   ├─ make check-compatibility
   ├─ make audit-runtime
   ├─ make inspect-policy
   └─ make compare-baseline (optional)
```

Entry point: `python -m newsroom.cli` or `newsroom-runtime-index` console scripts.

## Validation flow

```
Artifacts on disk
        │
        v
┌───────────────────┐
│ validate / build  │  observability/*.py (stdlib)
└─────────┬─────────┘
          │
          v
   OK | WARNING | FAIL
          │
          v
   exit 0 / 1 (--strict treats WARNING as fail)
```

No background validator daemons — validation runs on demand via CLI/Makefile.

## Release flow

```
make ci-test (runtime + smoke + contracts)
        │
        v
make runtime-nightly (staging)
        │
        v
inspection sequence (RELEASE_CHECKLIST.md)
        │
        v
git tag + CHANGELOG.md
```

**Release discipline > deployment automation.** No in-repo production deploy pipeline.

## Deployment flow

```
.env.example | deploy/example.env.production-lite
        │
        v
┌───────────────┐     ┌─────────────────────┐
│ venv / Docker │     │ systemd timer       │
│ app.main      │     │ newsroom-nightly    │
└───────────────┘     └─────────────────────┘
```

No Kubernetes, Helm, Terraform, or Ansible in this repository.

## Artifact flow (frozen lifecycle)

```
 1 health_snapshot
 2 runtime_report
 3 runtime_manifest
 4 recovery_report
 5 compatibility_report
 6 qualification_history
 7 audit_snapshot
 8 runtime_baseline      (optional)
 9 drift_report          (optional)
10 runtime_capabilities
11 capability_report
12 runtime_policy
13 policy_report
14 runtime_index         (written last)
```

## Docs topology

```
docs/START_HERE.md          ← onboarding hub
docs/ARCHITECTURE_MAP.md    ← this file
docs/ENGINEERING_PHILOSOPHY.md
docs/FAQ.md
docs/CONTRIBUTING.md
docs/OPERATOR_QUICKSTART.md
docs/DEPLOYMENT_QUICKSTART.md
docs/RUNTIME_OPS.md
docs/architecture/          ← ADRs + RUNTIME_CONTRACTS
```

## CLI topology

| Layer | Location |
|-------|----------|
| Unified nightly | `tools/runtime_ops.py` |
| Inspection | `newsroom/cli/__main__.py` |
| Makefile wrappers | `Makefile` (`OUTPUT_DIR`, `RUNTIME_DIR`) |
| Demo scripts | `examples/demo_walkthrough/*.sh` |

## Related

- [RUNTIME_LAYOUT_REFERENCE.md](RUNTIME_LAYOUT_REFERENCE.md)
- [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md)
- [RUNTIME_MATURITY.md](architecture/RUNTIME_MATURITY.md)
