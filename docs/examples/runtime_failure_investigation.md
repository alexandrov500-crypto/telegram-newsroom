# Example: runtime failure investigation

Operator workflow when `runtime_index` or nightly exits non-zero. **Inspection only** — no automatic remediation.

## Symptoms

- `make runtime-nightly` exits `1`
- `index_status` = `FAIL` or `WARNING`
- `incident_level` = `ERROR` in `runtime_report.json`

## CLI sequence

```bash
export OUTPUT_DIR=./runtime_ops_output

# 1) Catalog — what is missing or out of order?
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
python -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --json | head -40

# 2) Health + incident narrative
make runtime-health OUTPUT_DIR="$OUTPUT_DIR"
python -m newsroom.cli health --path "$OUTPUT_DIR" --report

# 3) Step-level failures from ops report sidecar
cat "$OUTPUT_DIR/runtime/health_snapshot.json" | python -m json.tool
# Inspect failed_steps[] and pipeline_status

# 4) Integrity
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"

# 5) Schema / recovery if bundle step failed
make check-compatibility OUTPUT_DIR="$OUTPUT_DIR"
make validate-recovery OUTPUT_DIR="$OUTPUT_DIR"
```

## Expected outputs (healthy reference)

| Command | Field | OK value |
|---------|-------|----------|
| `runtime-index` | `index_status` | `OK` |
| `health --report` | `incident_level` | `NONE` |
| `verify-runtime` | `verification_status` | `OK` |
| `validate-recovery` | `recovery_status` | `OK` |

Sanitized OK samples: [examples/runtime_samples/](../../examples/runtime_samples/).

## Incident reasoning

1. **Missing required artifact** — index lists `missing_required_artifact:*`; re-run nightly or check disk permissions on `$OUTPUT_DIR/runtime/`.
2. **Checksum mismatch** — `verify-runtime` FAIL; manifest stale after manual edit; run `make runtime-manifest` only if you understand regeneration semantics.
3. **Failed pipeline step** — `health_snapshot.failed_steps` names the ops step; open parent `nightly-check` log / journald for that step.
4. **Policy / guardrail** — `inspect-policy` FAIL; configuration violates frozen guardrails (e.g. history limit).

## Strict escalation

```bash
python -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --strict
```

Exits `1` on `WARNING` or `FAIL` — use before release gates.

## Non-goals

- No auto-heal daemon, no ticket system integration in-repo.
- Do not add new runtime artifact types to “fix” investigation — use existing reports.

See also: [OPERATOR_QUICKSTART.md](../OPERATOR_QUICKSTART.md), [RELEASE_CHECKLIST.md](../RELEASE_CHECKLIST.md).
