# RFC-010: Chaos / fault injection (test-only)

**Status:** Draft · **Target:** v1.2 test harness

## Problem

Failure drills cover **offline** inspection trees; live pipeline fault paths (Redis flap, enqueue failure after ack) lack automated reproduction.

## Proposal

- `NEWSROOM_CHAOS=1` only honored when `NEWSROOM_ENV=test` or pytest marker `chaos`.
- Hooks (monkeypatch points):
  - `transport.enqueue` raise after ack
  - Redis `SET` fail for publish lock
  - OpenAI 429 burst
- Tests in `tests/chaos/` (optional suite, not in default `ci-test`).

## Non-goals

- Production chaos daemon
- Modifying frozen drill fixtures under `examples/failure_drills/`

## Acceptance

- Zero effect when env unset
