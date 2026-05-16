# Contributing

Thanks for improving clarity without expanding frozen runtime governance.

## Local setup

```bash
python3.12 -m venv .venv && source .venv/bin/activate
make install-dev
cp .env.example .env   # placeholders only; never commit secrets
make install-dev   # installs requirements-dev.txt (pinned pytest, ruff)
make quality       # contracts + smoke + lint + format-check
make ci-test       # CI-equivalent sectioned pytest
```

See [QUICKSTART.md](QUICKSTART.md) for first app run. Post-v1 mode: [MAINTENANCE_MODE.md](MAINTENANCE_MODE.md) · Issues: [ISSUE_TRIAGE.md](ISSUE_TRIAGE.md).

## Coding philosophy

- Match existing module style (stdlib-first in `observability/`, thin CLIs).
- Prefer small, testable functions over frameworks.
- Keep editorial and ops paths separable.
- **Complexity growth requires exceptional justification** — especially new runtime artifacts, categories, or inspection commands.

## Deterministic runtime principles

- Preserve `KEY_ORDER` tuples when writing JSON.
- Bump `schema_version` only via documented compatibility rules (ADR-009).
- Do not reorder lifecycle generation without ADR + contract test updates.
- Atomic writes: `.tmp` + `os.replace` pattern already used — follow it.

## Testing philosophy

| Suite | Purpose |
|-------|---------|
| `tests/runtime/` | Ops modules, preflight, bundles |
| `tests/smoke/` | Artifact builders end-to-end |
| `tests/contracts/` | Frozen filenames, docs layout, navigation |

Run before PR: `make ci-test`.

Adding a contract test is preferred over ad hoc validation scripts.

## Contract freeze rules

**Do not** (without ADR + contract updates + maintainer agreement):

- Add `runtime/*.json` artifact types
- Add inspection CLI commands to the frozen registry
- Change lifecycle order or category taxonomy
- Add governance modules under `observability/` that imply enforcement

**Do** (encouraged):

- Docs, examples, demo scripts, Makefile DX
- Bug fixes in existing builders
- Additive optional JSON fields at schema v1 per compatibility rules

## Non-goals for contributions

- MkDocs/Docusaurus or web doc portals
- Kubernetes/Helm/Terraform/Ansible manifests
- Deployment orchestration, autoscaling, service mesh
- Runtime daemons, policy enforcement agents, browser admin UI
- New metrics platforms as hard dependencies

## PR guidelines

1. One concern per PR when possible (code vs docs).
2. Link relevant ADR or doc if touching operational semantics.
3. Include test updates for behavior changes.
4. No secrets, real tokens, or live channel IDs in fixtures.
5. Use sanitized samples under `examples/` for demos.

## Related

- [ENGINEERING_PHILOSOPHY.md](ENGINEERING_PHILOSOPHY.md)
- [architecture/RUNTIME_CONTRACTS.md](architecture/RUNTIME_CONTRACTS.md)
- [START_HERE.md](START_HERE.md)
