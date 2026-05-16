# ADR-029: Live Telegram operational validation (v3.x)

## Status

Accepted (bounded tests + opt-in live + read-only diagnostics)

## Context

Preservation and legacy stewardship established long-term posture. Production confidence requires controlled validation against real Telegram behavior without spam or contract drift.

## Decision

1. Publish live validation plan, governance, operator checklist.
2. Add `tests/live/` with CI-safe bounded tests and `live_telegram` opt-in marker.
3. Add `tools/live_telegram_diagnostics.py` (read-only; no API calls).
4. No change to frozen runtime artifacts; no mandatory live CI.

## Consequences

- Clear path for staging/live validation
- Telegram-safe bounded automated coverage
- Operator accountability via checklist

## Non-goals

- Mass production rollout, load testing, K8s migration, autonomous remediation
