# Deployment checksum notes — v3.1-production-lite

Deterministic integrity references for operators (not a supply-chain SBOM).

## Git release pointer

| Field | Value |
|-------|-------|
| Tag | `v3.1-production-lite` |
| Branch | `v3-live-telegram-validation` |
| Recorded at | 2026-05-16 |

After tagging locally, record:

```bash
git rev-parse v3.1-production-lite
# RELEASE_COMMIT_SHA:
```

**Recorded:** `1d46b4f94b44ea823b3cc4320631222ab3f0ca34` (`git rev-parse v3.1-production-lite^{commit}`)

## Source tree checksum (optional)

```bash
git archive --format=tar.gz v3.1-production-lite | shasum -a 256
# ARCHIVE_SHA256=
```

## Runtime inspection bundle

Frozen contract files (schema v1) — verify after nightly on host:

```bash
make verify-runtime OUTPUT_DIR=./runtime_ops_output
make runtime-manifest OUTPUT_DIR=./runtime_ops_output
```

Manifest SHA256 recorded in `runtime/runtime_manifest.json` — compare across deploys for drift detection.

## Python environment

```bash
python3 --version
pip freeze | shasum -a 256
# ENV_FREEZE_SHA256=
```

Pin production host to same minor Python as CI (3.11+).

## Configuration checksum (redacted)

Do not commit `.env`. Operator records locally:

```bash
shasum -a 256 .env   # store in secure ops vault only
```

## Post-deploy verification

| Check | Command |
|-------|---------|
| App import | `python3 -c "from app.config import load_settings"` |
| Diagnostics | `make live-telegram-diagnostics` |
| Strict env | `python3 tools/staging_environment_verify.py --strict` |

## Integrity failure

If archive SHA or manifest checksum differs unexpectedly:

1. `DRY_RUN=true`
2. Do not publish
3. Compare tag vs deployed tree
4. Open incident [incident_response.md](../runbooks/incident_response.md)
