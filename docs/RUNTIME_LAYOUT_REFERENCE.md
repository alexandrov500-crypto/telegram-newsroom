# Runtime layout reference

Layout under ops output directory `{output_dir}` (default `./runtime_ops_output`).

```
{output_dir}/
  qualification.json          # optional sidecar (qualification step)
  runtime_bundle.zip          # optional zip from bundle step
  ops_benchmark.json          # optional benchmark sidecar
  runtime/
    health_snapshot.json
    runtime_report.json
    runtime_manifest.json
    recovery_report.json
    compatibility_report.json
    qualification_history.json
    audit_snapshot.json
    runtime_baseline.json
    drift_report.json
    runtime_capabilities.json
    capability_report.json
    runtime_policy.json
    policy_report.json
    runtime_index.json
```

## Artifact catalog

| File | Category | Required | Producer | Primary CLI |
|------|----------|----------|----------|-------------|
| `health_snapshot.json` | health | yes | nightly → `health_snapshot` | `health` |
| `runtime_report.json` | reporting | yes | nightly → `runtime_report` | `health --report` |
| `runtime_manifest.json` | verification | yes | nightly → `runtime_manifest` | `verify-runtime` |
| `recovery_report.json` | recovery | yes | nightly → `validate_runtime_recovery` | `validate-recovery` |
| `compatibility_report.json` | compatibility | yes | nightly → `build_compatibility_report` | `check-compatibility` |
| `qualification_history.json` | audit | yes | nightly → `update_runtime_history` | `audit-runtime` |
| `audit_snapshot.json` | audit | yes | nightly → `update_runtime_history` | `audit-runtime` |
| `runtime_baseline.json` | baseline | no | manual / `create-baseline` | `create-baseline` |
| `drift_report.json` | baseline | no | nightly / `compare-baseline` | `compare-baseline` |
| `runtime_capabilities.json` | capabilities | yes | nightly → `update_runtime_capabilities` | `inspect-capabilities` |
| `capability_report.json` | capabilities | yes | nightly → `update_runtime_capabilities` | `inspect-capabilities` |
| `runtime_policy.json` | policy | yes | nightly → `update_runtime_policy` | `inspect-policy` |
| `policy_report.json` | policy | yes | nightly → `update_runtime_policy` | `inspect-policy` |
| `runtime_index.json` | reporting | yes | nightly → `update_runtime_index` (last) | `runtime-index` |

## Generation order (frozen)

1 → 14 as listed in `runtime/` table above; `runtime_index.json` is always **last**.

Contracts: [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md).
