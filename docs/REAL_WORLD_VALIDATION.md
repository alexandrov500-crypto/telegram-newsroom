# Real-world validation (v1.0.0)

Engineering reality-check performed on a clean working tree. **No architecture changes** — findings drove docs and operator-message polish only.

## Validated workflows

| Step | Command | Result |
|------|---------|--------|
| Clone / open tree | — | Repo layout matches [REPOSITORY_MAP.md](REPOSITORY_MAP.md) |
| Install | `make install-dev` | Requires Python **3.12+** and network for `requirements.txt`; on 3.14 some wheels may fail until pins widen |
| Env template | `cp .env.example .env` | Placeholders clear; secrets not in repo |
| Preflight | `make runtime-preflight` | Needs `RUNTIME_DIR` with live state for full soak path |
| Nightly | `make runtime-nightly` | Needs valid `.env` + `RUNTIME_DIR`; writes `OUTPUT_DIR/runtime/*` |
| Index | `make runtime-index` | Clear FAIL when artifacts missing; lists lifecycle order |
| Verify | `make verify-runtime` | Actionable checksum / missing lists |
| Release gate | `make release-check` | contracts → smoke → quality → packaging (maintainer) |

**Demo without live nightly:** use [examples/demo_walkthrough/](../examples/demo_walkthrough/) (`DEMO_RUN=0` default) and read [examples/demo_outputs/](../examples/demo_outputs/) — do **not** use `examples/runtime_samples/` for `verify-runtime` (placeholder checksums).

## Operator friction findings

| Finding | Severity | Resolution |
|---------|----------|------------|
| Empty `OUTPUT_DIR` → index FAIL with long missing list | Low | Expected; added **Operator actions** footer in CLI summaries |
| `examples/runtime_samples/` used with `verify-runtime` → checksum FAIL | Medium | Documented in verify summary + this doc |
| `make release-check` vs `make release-qualify` naming | Low | Already split; reinforced in docs/tests |
| `OUTPUT_DIR` is Makefile-only, not in `.env` | Low | Clarified in DEPLOYMENT_QUICKSTART table |
| Top-level `python -m newsroom.cli --help` is abbreviated | Low | Per-command `--help` works; unknown command prints hint |
| Python 3.14 may fail `pip install` (pydantic-core wheel) | Medium | Documented; CI uses 3.12; `requires-python >=3.12` |
| Many onboarding docs | Low | [START_HERE.md](START_HERE.md) is hub; `make docs-map` lists roles |

## Fixes applied (this phase)

- Operator action footers on index / verify / compatibility FAIL|WARNING summaries.
- Unknown CLI command prints `make runtime-help` hint.
- Docs: [OPERATIONAL_CONFIDENCE.md](OPERATIONAL_CONFIDENCE.md), example disclaimers, RELEASE_PROCESS tag examples.
- Contract tests: [test_operational_validation.py](../tests/contracts/test_operational_validation.py).

## Remaining manual assumptions

- Operator provides Telegram + OpenAI credentials in `.env`.
- `runtime-nightly` is not run in CI on every PR (bounded local/scheduled job).
- Live `RUNTIME_DIR` exists for meaningful soak/bundle steps.
- Bundle qualification remains `make release-qualify` (separate from `make release-check`).
- No enterprise SLA — see [LTS_NOTES.md](LTS_NOTES.md).

## Related

- [OPERATIONAL_CONFIDENCE.md](OPERATIONAL_CONFIDENCE.md) · [OPERATOR_QUICKSTART.md](OPERATOR_QUICKSTART.md) · [RELEASE_FINALIZATION.md](RELEASE_FINALIZATION.md)
