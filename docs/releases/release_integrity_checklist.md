# Release integrity checklist — v3.1-production-lite

Execute before and after tagging.

## Repository hygiene

- [ ] `git status` clean (no untracked secrets)
- [ ] `.env` in `.gitignore` only — not tracked
- [ ] No `*.session` files tracked
- [ ] No API keys in `git log -p` (spot check)
- [ ] `SECURITY_REDACTION=1` for shared logs

## Test gates

```bash
make ci-test
make live-validation-validate
make governance-validate
make resilience-validate
make staging-validate
make production-validate   # after merge
```

All must exit 0.

## Runtime parity

- [ ] `make verify-runtime` on reference OUTPUT_DIR (WARNING acceptable for optional artifacts)
- [ ] `make check-compatibility` → schema version 1
- [ ] No new required files under `runtime/` without ADR

## Documentation parity

- [ ] `docs/releases/v3.1-production-lite.md` current
- [ ] `CHANGELOG.md` [Unreleased] section updated
- [ ] `docs/v3_live_telegram_validation_report.md` grade **A**
- [ ] `docs/START_HERE.md` links activation docs

## Tag integrity

```bash
git tag -v v3.1-production-lite   # if signed tags enabled
git rev-parse v3.1-production-lite
git log -1 --oneline v3.1-production-lite
```

Record tag SHA in [deployment_checksum_notes.md](deployment_checksum_notes.md).

## Deployment artifact

- [ ] Docker image tag matches release (if used)
- [ ] `deploy/example.env.production-lite` reviewed
- [ ] Operator has rollback block from [controlled_activation.md](../runbooks/controlled_activation.md)

## Post-release

- [ ] GitHub release notes from `v3.1-production-lite.md`
- [ ] 72h stability window started on production host
- [ ] Baseline diagnostics JSON archived
