# v1.3 resilience validation report

**Branch:** `v1.3-resilience-engineering`  
**Scope:** Long-running stability, drift, retention — no contract changes

---

## Soak test summary

| Suite | Tests | Mode |
|-------|-------|------|
| `tests/soak/test_soak_harness.py` | Harness + WAL churn | CI bounded |
| `tests/soak/test_drift_monitor.py` | Drift baselines | CI |
| `tests/soak/test_retry_storm_resistance.py` | Burst bounds | CI |
| `tests/soak/test_resource_stability.py` | RSS/task samples | CI |
| `tests/soak/test_scheduler_stability.py` | Overlap/lag | CI |
| `tests/soak/test_evidence_retention.py` | CLI tooling | CI |
| `tests/soak/test_snapshot_retention_cycles.py` | Restore cycles | CI |
| Existing `test_soak_simulation_smoke.py` | Simulation profiles | CI |

Run: `make soak-test` · Extended local: `SOAK_EXTENDED=1 make soak-test`

---

## Runtime drift findings

- **Config drift:** detected when opt-in flags change between baselines
- **WAL growth:** warning when growth % exceeds threshold
- **Evidence growth:** warning on large `OUTPUT_DIR` expansion
- **Retry amplification:** burst window vs `RUNTIME_RETRY_STORM_COUNT`

Module: `utils/runtime_drift_monitor.py` (opt-in `RUNTIME_DRIFT_MONITOR=1`)

---

## Memory stability findings

- In-process metrics and runtime events remain bounded (ring buffers)
- Soak harness captures RSS samples without mandatory profilers
- No leak detected in bounded CI soak; extended runs are operator-owned

---

## SQLite longevity assessment

- WAL churn observable and checkpoint path documented
- Multi-writer remains **unsafe** (unchanged)
- Integrity check recommended after maintenance windows

---

## Retry storm recovery assessment

- Retry policy caps delay ≤ 300s base (+ jitter)
- Worker retry deque maxlen 512
- `WORKER_RETRY_SAFE` validated in chaos suite; default legacy path documented

---

## Scheduler stability assessment

- APScheduler `max_instances=1`, `coalesce=True` on pipeline job
- Opt-in `SCHEDULER_DIAGNOSTICS=1` records wall time, overlap, lag
- Overlap detection available in diagnostics snapshot

---

## Operational sustainability grade

**A- (production-lite, with maintenance discipline)**

Requires: daily nightly, weekly drift/backup, monthly DB checkpoint, retention prune.

---

## Recommended maintenance intervals

| Task | Interval |
|------|----------|
| `runtime-nightly` | Daily |
| `backup_cli` | Daily (quiesced) |
| Evidence prune | Weekly |
| WAL checkpoint | Weekly–monthly |
| Process restart | Monthly |
| Full `make resilience-validate` | Per release candidate |

---

## Maximum safe deployment envelope

See [v1_3_operational_envelope.md](v1_3_operational_envelope.md).

---

## Remaining long-term risks

- Months-long uptime without checkpoint → WAL/disk pressure
- Legacy retry path if `WORKER_RETRY_SAFE=0` under enqueue failures
- Evidence directory unbounded without operator prune
- Live API outages still require human runbook execution

---

## Validation commands

```bash
make ci-test
make release-check
make chaos-test
make soak-test
make drift-validate
make resilience-validate
```
