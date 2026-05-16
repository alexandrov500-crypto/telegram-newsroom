# Release finalization (v1.0.0)

Manual checklist for tagging a stable release. **No automated release bots or semantic-release.**

## 1. Version bump (if not already 1.0.0)

Single source of truth: `newsroom/_version.py` (`VERSION`, `RELEASE_STATUS`).

- `pyproject.toml` reads version via `newsroom.__version__`
- `app/versioning.APP_VERSION` re-exports package version
- Update [CHANGELOG.md](../CHANGELOG.md)

## 2. CI-equivalent tests

```bash
make ci-test
```

Sections: runtime → smoke → contracts.

## 3. Release readiness gate

```bash
make release-check
```

Sections: contracts → smoke → quality → packaging consistency.

## 4. Production burn-in (recommended before first production tag)

- Follow [BURN_IN_REPORT.md](BURN_IN_REPORT.md) (7-day checklist).
- Run [FAILURE_DRILLS.md](FAILURE_DRILLS.md) against `examples/failure_drills/`.
- Practice [RESTORE_PROCEDURE.md](RESTORE_PROCEDURE.md) with `backup_cli` on a staging host.

## 5. Runtime validation (staging host)

```bash
export OUTPUT_DIR=./runtime_ops_output
make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR="$OUTPUT_DIR"
make runtime-index OUTPUT_DIR="$OUTPUT_DIR"
python -m newsroom.cli verify-runtime --path "$OUTPUT_DIR" --strict
```

See [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md).

## 6. Bundle qualification (optional)

Compare zip bundles against a known baseline:

```bash
make release-qualify RUNTIME_BUNDLE=./artifacts/runtime_bundle.zip BASELINE=./baselines/runtime_bundle.zip
```

## 7. Changelog and tag

1. Finalize `CHANGELOG.md` section for `v1.0.0`.
2. Commit with message describing release scope.
3. Tag: `git tag -a v1.0.0 -m "v1.0.0 stable — frozen runtime governance"`

## 8. Rollback expectations

- **Code:** checkout previous tag.
- **Data:** restore `backup_cli` archive; do not mix Alembic revisions casually.
- **Ops artifacts:** `OUTPUT_DIR` is disposable — regenerate with nightly.

## Non-goals

- GitHub Actions production deployment
- Container registry promotion in CI
- Terraform/Helm/Kubernetes release pipelines

**Release discipline is preferred over deployment automation.**
