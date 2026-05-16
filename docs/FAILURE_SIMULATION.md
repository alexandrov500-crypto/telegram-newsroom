# Failure simulation (controlled degradation)

Failure drills are **test-local** helpers under `tests/helpers/failure_injection.py`. They patch Redis health, corrupt JSON files, or drive DB shutdown — no external chaos platforms.

## Scenarios covered

| Scenario | Mechanism | Expected behavior |
|----------|-----------|---------------------|
| Redis unavailable | `get_redis` → `None` with `redis_enabled=True` | `gather_runtime_health` reports `degraded_connect_failed`; overall health may stay `ok` (Redis optional by design). |
| Redis ping failure | Fake client + `redis_ping_ok` → `False` | Redis check `ok: false`; full snapshot `ok: false`. |
| DB unavailable | `close_db()` then health probe | Database check fails; snapshot `ok: false`. |
| Malformed timeline JSON | Invalid file on disk | `validate_operational_timeline` reports `invalid_json_on_disk`. |
| Malformed job envelope | `MALFORMED_JOB_ENVELOPE` constant (invalid JSON) | `JobEnvelope.from_json` raises; worker/transport must reject poison payloads. |
| Stuck lease / visibility | In-memory transport: no ack past visibility + `recover_stale` | Job returns to pending; see `tests/failure/test_failure_visibility_recovery.py`. |
| Schema drift (suppression) | `duplicate_burst` not an object | `validate_suppression_state` flags schema issue. |

## Reports

Use `utils/evidence_reports.build_failure_report` to emit JSON or lightweight HTML from a dict produced by your drill harness (the repo tests construct small payloads inline).

## Recovery

See `docs/RUNTIME_CHARACTERISTICS.md` for Redis reconnect (`utils.redis_client.reconnect_redis`), DLQ replay (`admin_cli dlq-replay`), and suppression emergency reset (`runtime-reset-suppression`). Automated smoke checks live under `tests/recovery/` (cadence/timeline persistence, Redis reconnect idempotency when disabled).

## Safety

Patches are scoped with `contextlib` / `unittest.mock` and must not run against production processes from unit tests. For staging drills, prefer explicit maintenance windows and captured exports (`--json-out`).
