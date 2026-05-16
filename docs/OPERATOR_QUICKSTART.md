# Operator quickstart (production-lite, v1.0.0)

Operator-focused guide for runtime inspection on a **stable** frozen governance model. Not platform architecture — see [START_HERE.md](START_HERE.md) · [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md) · [architecture/SYSTEM_OVERVIEW.md](architecture/SYSTEM_OVERVIEW.md).

**Prerequisites:** Python 3.12+ (recommended), repo installed (`make install-dev`), `OUTPUT_DIR` writable (default `./runtime_ops_output` — Makefile variable, not in `.env`).

**Demo JSON only:** [examples/runtime_samples/](../examples/runtime_samples/) — not for `verify-runtime` (placeholder checksums). Use after `make runtime-nightly` or see [demo_outputs/](../examples/demo_outputs/).

## Minimal production-lite deployment

1. Configure `.env` (see [QUICKSTART.md](QUICKSTART.md), [DEPLOYMENT.md](DEPLOYMENT.md)).
2. Run live services (bot/scheduler) per your layout.
3. Schedule or run nightly ops:

```bash
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR=./runtime_ops_output
```

4. Inspect results (below). Gate releases with [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## 5-minute operational walkthrough

```bash
export OUTPUT_DIR=./runtime_ops_output

# 1) Unified catalog (start here)
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"

# 2) Health + incident
make runtime-health OUTPUT_DIR="$OUTPUT_DIR"
make runtime-report OUTPUT_DIR="$OUTPUT_DIR"

# 3) Integrity
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"

# 4) Recovery + schema
make validate-recovery OUTPUT_DIR="$OUTPUT_DIR"
make check-compatibility OUTPUT_DIR="$OUTPUT_DIR"

# 5) Audit trail
make audit-runtime OUTPUT_DIR="$OUTPUT_DIR"
```

All commands are **offline inspection** except `runtime-nightly`, which runs the bounded ops pipeline.

## Nightly-check lifecycle

After `make runtime-nightly`, artifacts appear under `$OUTPUT_DIR/runtime/` in fixed order (see [RUNTIME_LAYOUT_REFERENCE.md](RUNTIME_LAYOUT_REFERENCE.md)). The last file written is `runtime_index.json`.

## Common inspection commands

| Goal | Command |
|------|---------|
| Table of contents | `python -m newsroom.cli runtime-index --path $OUTPUT_DIR` |
| Health counters | `python -m newsroom.cli health --path $OUTPUT_DIR` |
| Incident summary | `python -m newsroom.cli health --path $OUTPUT_DIR --report` |
| Checksums | `python -m newsroom.cli verify-runtime --path $OUTPUT_DIR --strict` |
| Recovery | `python -m newsroom.cli validate-recovery --path $OUTPUT_DIR --strict` |
| Replay bundle (temp extract) | `python -m newsroom.cli replay-runtime --path $OUTPUT_DIR` |
| Schema versions | `python -m newsroom.cli check-compatibility --path $OUTPUT_DIR --strict` |
| Qualification history | `python -m newsroom.cli audit-runtime --path $OUTPUT_DIR` |
| Baseline snapshot | `python -m newsroom.cli create-baseline --path $OUTPUT_DIR` |
| Drift vs baseline | `python -m newsroom.cli compare-baseline --path $OUTPUT_DIR --strict` |
| Capabilities / policy | `inspect-capabilities`, `inspect-policy` |

Discoverability: `make runtime-help`.

## Failure investigation workflow

1. **`runtime-index`** — what exists? `index_status` OK?
2. **`health --report`** — `incident_level` and `failed_steps`?
3. **`verify-runtime --strict`** — checksum / missing required?
4. **`validate-recovery --strict`** — structure and bundle extractable?
5. **`check-compatibility --strict`** — `schema_version` aligned?
6. **`audit-runtime`** — recent qualification FAIL/WARNING counts?
7. **`compare-baseline --strict`** — drift since known-good (if baseline present)?

Fix filesystem or re-run `runtime-nightly`; do not expect tools to mutate live pipeline state.

## Strict mode for CI

Append `--strict` to inspection commands to exit non-zero on `WARNING` or `FAIL`. Example:

```bash
python -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --strict
```

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## What good output looks like

```text
Index status: OK
Verification status: OK
Recovery status: OK or WARNING (optional zip only)
Compatibility status: OK
```

After nightly: all 12 required files under `runtime/` show `(present)` in `make runtime-index`.

## Common operator mistakes

| Mistake | Symptom | Fix |
|---------|---------|-----|
| Inspecting before nightly | Many `(missing)` | `make runtime-nightly` first |
| Using `examples/runtime_samples/` for verify | checksum FAIL | Use real `OUTPUT_DIR` |
| Confusing `OUTPUT_DIR` with `RUNTIME_STATE_DIR` | Wrong paths | See DEPLOYMENT_QUICKSTART table |
| Expecting tools to auto-fix JSON | No mutation | Re-run nightly |
| `make release-check` vs `release-qualify` | Wrong command | release-check = tests; release-qualify = zip compare |

## Corrupted runtime state

Signals: `checksum_mismatches`, widespread `(missing)`, `compatibility_status: FAIL`.  
Drills: [FAILURE_DRILLS.md](FAILURE_DRILLS.md) · `scripts/runtime_sanity_check.sh`

## When NOT to use runtime_samples

[examples/runtime_samples/](../examples/runtime_samples/) are **documentation fixtures** with placeholder checksums. Always validate against a real nightly `OUTPUT_DIR`.
