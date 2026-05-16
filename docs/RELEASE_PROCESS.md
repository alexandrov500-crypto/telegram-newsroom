# Release process (production-lite v1)

How to cut an operational release without expanding runtime architecture. **Release discipline is preferred over deployment automation** — verify locally or in CI, tag, document; do not rely on an in-repo deploy orchestrator.

**Related:** [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) · [CHANGELOG.md](../CHANGELOG.md) · [architecture/RUNTIME_MATURITY.md](architecture/RUNTIME_MATURITY.md)

## Version tagging

- Use semantic tags: `v1.0.0`, `v1.0.1`, `v1.0.2` (patch), `v2.0.0` (breaking).
- Update [CHANGELOG.md](../CHANGELOG.md) with date and milestone bullets.
- Tag only after pre-release verification passes (below).
- Record git SHA in release notes; store operator `.env` version outside the repo.

## Pre-release verification

1. **Environment:** `.env` from `.env.example` or `deploy/example.env.production-lite` (no secrets in git).
2. **Install:** `make install-dev`.
3. **Optional live check:** `make runtime-nightly` on a staging host.

## Smoke and contract tests

```bash
make ci-test
# equivalent:
python3 -m pytest tests/runtime tests/smoke tests/contracts -q --tb=short
```

Contract suites:

- `tests/contracts/test_runtime_contracts.py` — frozen governance contracts.
- `tests/contracts/test_release_layout.py` — deploy templates, samples, release docs.

## Runtime validation sequence

On a known-good or fresh nightly `OUTPUT_DIR`:

```bash
export OUTPUT_DIR=./runtime_ops_output
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
make verify-runtime OUTPUT_DIR="$OUTPUT_DIR"
make validate-recovery OUTPUT_DIR="$OUTPUT_DIR"
make check-compatibility OUTPUT_DIR="$OUTPUT_DIR"
make inspect-policy OUTPUT_DIR="$OUTPUT_DIR"
make inspect-capabilities OUTPUT_DIR="$OUTPUT_DIR"
```

Strict gate (recommended for release candidates):

```bash
python -m newsroom.cli runtime-index --path "$OUTPUT_DIR" --strict
python -m newsroom.cli verify-runtime --path "$OUTPUT_DIR" --strict
python -m newsroom.cli validate-recovery --path "$OUTPUT_DIR" --strict
python -m newsroom.cli check-compatibility --path "$OUTPUT_DIR" --strict
python -m newsroom.cli inspect-policy --path "$OUTPUT_DIR" --strict
```

Full checklist: [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## Rollback philosophy

- **Code:** redeploy previous git tag or container image digest.
- **Database:** restore from `backup_cli` zip taken before upgrade; do not mix Alembic revisions casually.
- **Runtime JSON:** restore `RUNTIME_STATE_DIR` from backup or accept regeneration (editorial memory may reset).
- **Ops artifacts:** `OUTPUT_DIR` is disposable; re-run `make runtime-nightly` after rollback.

No automated rollback controller — operators execute steps deliberately.

## Release artifact expectations

| Artifact | Expectation |
|----------|-------------|
| Git tag | Annotated tag matching CHANGELOG section |
| CHANGELOG | User-visible operational changes only |
| `runtime_ops_output/runtime/` | Optional attachment for post-mortems (not published by default) |
| `runtime_bundle.zip` | From nightly; used by qualification/regression |
| Backup zip | Operator-maintained; not part of git release |

## What we do not ship

- Kubernetes manifests, Helm, Terraform, Ansible playbooks.
- CI deployment to production environments.
- Autoscaling, service mesh, or web admin panels.
- New runtime governance JSON types (frozen per ADR-015).

## Post-release

- Monitor live process logs and optional `TELEGRAM_STARTUP_NOTIFY`.
- Schedule `newsroom-nightly.timer` or cron for continued ops discipline.
- Operators use [DEPLOYMENT_QUICKSTART.md](DEPLOYMENT_QUICKSTART.md) for onboarding new hosts.
