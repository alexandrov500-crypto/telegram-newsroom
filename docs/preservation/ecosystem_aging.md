# Ecosystem aging assessment

Realistic survivability outlook for a production-lite newsroom — not enterprise risk register theater.

## Summary horizon

| Horizon | Posture |
|---------|---------|
| 1–2 years | Maintain pins; security patches; CI green |
| 3–5 years | Planned Python uplift; API drift monitoring |
| 5+ years | Recovery-from-archive scenario; possible minor/major bump |

## Component outlook

| Component | Survivability | Replacement difficulty | Operational impact | Time horizon |
|-----------|---------------|------------------------|--------------------|--------------|
| **Python (≥3.12)** | Good if uplift tracked | Medium — test suite | CI/dev breakage | EOL-driven (years) |
| **SQLite** | Excellent (file format) | Low for same use case | Single-file backup | 10+ years |
| **Redis** | Good while maintained | Medium — queue/lock rewrite | Multi-worker degraded without it | 5–10 years |
| **Telethon** | Moderate — Telegram API drift | High — core ingest | Ingest stops if broken | 2–5 years watch |
| **aiogram** | Moderate — major versions | High — admin bot | Moderation path breaks | 2–5 years watch |
| **APScheduler** | Good for in-process | Low–medium | Scheduler overlap/missed jobs | 5+ years |
| **OpenAI API** | Volatile by design | Medium — client bumps | Pipeline/JSON schema | Continuous |
| **SQLAlchemy** | Good | Medium if ORM patterns deep | Migrations | 5+ years |
| **Packaging (pip/setuptools)** | Good | Low | Install friction | Ongoing |

## Python lifecycle risks

- **Risk:** `requires-python` lags EOL; CI uses only latest.
- **Mitigation:** Document floor in `pyproject.toml`; annual uplift drill.
- **Unsupported:** Guarantee on unsupported Python forever.

## SQLite longevity

- **Outlook:** Best preservation asset — copy quiesced file.
- **Risk:** Schema migrations not replayed on old backup.
- **Mitigation:** Keep migration chain in repo; ADR on major schema.

## Redis dependency aging

- **Outlook:** Optional for T1; critical for T2 multi-worker.
- **Risk:** Protocol/client changes in `redis` Py package.
- **Mitigation:** Pin major; T1 fallback documented.

## Telethon / Telegram sustainability

- **Risk:** Session format, API layer changes, ToS enforcement.
- **Impact:** Ingest and history fetch — core path.
- **Mitigation:** Pin telethon; monitor upstream; session rotation runbooks.

## APScheduler sustainability

- **Risk:** Low for single-process scheduler use.
- **Impact:** Missed pipeline if breaking change.
- **Mitigation:** `SCHEDULER_DIAGNOSTICS=1` on return from dormancy.

## OpenAI API evolution risk

- **Risk:** Model retirement, JSON mode, auth changes.
- **Impact:** Summarization/clustering — not SQLite.
- **Mitigation:** Model name in config; contract tests on JSON shapes where present.

## Packaging / toolchain drift

- **Risk:** `pip install` behavior, ruff/pytest pins stale.
- **Impact:** Dev/CI only — not runtime at rest.
- **Mitigation:** `requirements-dev.txt` pins; `make release-check`.

## Non-goals

- Vendoring entire PyPI
- Offline mirror platform
- Guaranteeing third-party API stability
