# Long-term recoverability guarantees

Honest bounds on what remains recoverable when active development stops.

## Should remain recoverable

| Asset | Confidence | Mechanism |
|-------|------------|-----------|
| Inspection evidence | **High** | Frozen schema v1 + verify-runtime |
| SQLite editorial DB | **High** | File copy when quiesced |
| Recovery procedure | **High** | validate-recovery, semantics docs |
| Decision history | **High** | ADRs + stewardship index |
| Tag-locked install | **High** | requirements.txt at tag |
| Operator runbooks | **Medium–High** | Markdown in repo |

## Realistically preservable (operator-owned)

| Asset | Notes |
|-------|-------|
| Complete OUTPUT_DIR snapshots | External disk; retention policy |
| Secrets | Out of repo; handoff secure store |
| Redis data | Not long-term SSOT — sqlite + DLQ review |
| CI green on future OS | Requires uplift, not automatic |

## May decay over time

| Item | Decay | Mitigation |
|------|-------|------------|
| Telethon/aiogram compatibility | API drift | Pin + uplift branch |
| OpenAI models | Retirement | Config model name update |
| Python installability | EOL | Document floor; uplift |
| Live Telegram sessions | Expiry | Re-auth runbooks |
| `main` without testing | Bitrot | Use **tags** |

## Dependency survivability assumptions

- Critical deps pinned at tag ([dependency_preservation.md](../preservation/dependency_preservation.md)).
- Optional redis/asyncpg `>=` may need resolution help on old pip — use tag lockfile.

## Archival usability expectations

Archive bundle (minimum):

- Git tag identifier
- `requirements.txt` + `pyproject.toml` from tag
- sqlite file
- Full required `runtime/` tree or nightly OUTPUT_DIR
- Redacted env example

**Usability:** a competent operator can pass `validate-recovery` within a maintenance window — not “click one button.”

## Recovery confidence levels

| Level | Meaning |
|-------|---------|
| **A** | Tag + full archive + docs → inspect + restore DB |
| **B** | Tag + sqlite only → editorial resume with effort |
| **C** | Repo clone only → dev rebuild; ops evidence lost |
| **D** | Partial files → unsupported |

Target for legacy stewardship: **A** for operators who follow preservation docs.

## Non-guarantees

- Exactly-once jobs after years idle
- Zero-downtime restore
- Automatic dependency resolution on future platforms
- Channel history replay from archive alone
