---
name: Feature request
about: Propose a change (maintenance-first project — high bar for complexity)
title: "[feature] "
labels: enhancement
---

## Summary

What do you want?

## Why is the existing operational model insufficient?

The project is **maintenance-first** after v1.0.0. Runtime governance is frozen (14 artifacts, 11 inspection CLIs).

Explain why current tools/docs/CLIs cannot address this:

## Why is complexity increase justified?

> New architectural layers require exceptional justification.

What maintenance cost does this add (deps, docs, contracts, operator cognitive load)?

## Why can this not be solved externally?

(e.g. host scripts, fork, external scheduler, your own Compose overlay — without changing frozen contracts)

## Category

- [ ] Application/editorial feature (does not add `runtime/*.json` types)
- [ ] Documentation / ergonomics only
- [ ] **Architecture expansion** (new governance, orchestration, telemetry platform) — expect scrutiny

## Checklist

- [ ] I read [docs/MAINTENANCE_MODE.md](../../docs/MAINTENANCE_MODE.md) and [docs/STABILITY_GUARANTEES.md](../../docs/STABILITY_GUARANTEES.md)
- [ ] I am not asking for new frozen `runtime/*.json` artifact types without a major version plan
