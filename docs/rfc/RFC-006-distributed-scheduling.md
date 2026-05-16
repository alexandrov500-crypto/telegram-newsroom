# RFC-006: Distributed scheduling (external only)

**Status:** Draft · **Target:** v1.2+ documentation-first

## Problem

`app/main.py` runs APScheduler in-process. Multiple app instances would duplicate pipeline ticks.

## Proposal

- **Do not** embed leader election in-repo (ADR-003).
- Document **external** triggers only:
  - systemd timer calling `python -m scheduler.jobs` one-shot, or
  - CronJob invoking existing job entrypoints with `PIPELINE_ENABLED=0` on passive nodes.
- Optional `SCHEDULER_MODE=embedded|external` (default `embedded`).

## Non-goals

- Celery beat, K8s operator, custom cron daemon in repo

## Migration risk

Medium (ops) — operators must ensure single active scheduler.
