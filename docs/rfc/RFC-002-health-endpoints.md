# RFC-002: Deep health vs liveness

**Status:** Draft · **Target:** v1.1 opt-in

## Problem

`docker/healthcheck.py` and HTTP liveness do not validate Telegram token, OpenAI reachability, or Redis when enabled.

## Proposal

- `HEALTH_PROFILE=liveness|deep` (default `liveness`).
- **Deep** (opt-in): bounded checks — config parse, DB ping, optional Redis PING, optional Telegram `getMe` with timeout; returns JSON `{status, checks:{...}}`.
- Add `--profile deep` to existing `newsroom.cli health` as additive flag only.

## Non-goals

- Continuous synthetic monitoring SaaS
- Changing frozen `health_snapshot.json` schema for nightly

## Acceptance

- Deep profile off by default; no extra network calls in default Docker HEALTHCHECK
