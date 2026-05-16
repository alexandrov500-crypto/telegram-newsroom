# Legacy state definition

What **legacy but supported** means for this production-lite newsroom — not abandoned, not hyperactive.

## Legacy but supported

| Property | Meaning |
|----------|---------|
| **Frozen contracts** | 14 runtime artifacts, schema v1, 11 CLIs — unchanged without v2 program |
| **Operable** | T1/T3 topologies still valid; inspection + recovery paths work |
| **Maintained** | Security pins, critical fixes, doc corrections — on cadence below |
| **Not expanding** | No new governance layers, platforms, or mandatory infra |

Legacy ≠ archive-only. Legacy = **low-change operational continuity**.

## Active vs passive stewardship

| Mode | Cadence | Activities |
|------|---------|------------|
| **Active stewardship** | Normal maintenance | Features opt-in; regular CI; releases as needed |
| **Passive stewardship** | Quarterly–annual | CVE pins, `preservation-validate`, recovery drill, doc fixes |
| **Dormant** | Years between touches | Tag-locked recovery; no promise of latest-main compatibility |

Passive is **supported** if recovery docs and pins at tag remain usable.

## Acceptable low-change cadence

| Activity | Legacy cadence |
|----------|----------------|
| Security dependency patch | As needed (CVE) |
| Planned release | 0–2 per year |
| ADR | Only for material semantic/contract change |
| New Makefile targets | Discouraged — link existing tools |
| Full dependency modernize | Rejected unless EOL forcing |

## Legacy operational expectations

- Operators run nightly/verify on their schedule — not enforced by project.
- Multi-worker requires same T2 discipline ([multi_worker_discipline.md](../scalability/multi_worker_discipline.md)).
- External APIs (Telegram, OpenAI) may drift — pins + uplift, not guarantees.

## Frozen-but-operable definition

**Frozen:** inspection contract, default-off flags preserving v1.0 paths, semantics docs.

**Operable:** app + worker + sqlite + optional redis; `make release-check` passes at supported tag.

## Stable legacy criteria

A release tag qualifies as **stable legacy** when:

1. `make ci-test` + `make release-check` green at tag
2. Validation report for phase captured in `docs/`
3. `requirements.txt` pins present
4. Recovery drill documented or report references drill
5. No known HIGH in guardrails at tag (advisory)

## Non-goals

- Perpetual feature evolution
- SLA for response time
- Guarantee latest upstream APIs without uplift work
