# Trust boundaries

## Trusted runtime surface

- `observability/` inspection builders (read-only validation)
- Frozen 14 JSON artifacts when produced by `runtime-nightly`
- `newsroom.cli` inspection commands

## Untrusted operator input

- `.env` values (validate via posture check)
- Restored snapshot trees (verify before trust)
- Manual edits to `OUTPUT_DIR/runtime/*.json`

## External dependencies

| Dependency | Trust assumption |
|------------|------------------|
| Telegram API | Authentic channel/admin actions |
| OpenAI API | Confidential prompts; no training opt-out in-repo |
| Redis | Network-private; AUTH recommended |

## Redis trust assumptions

- Network not exposed to internet
- `REDIS_URL` treated as secret
- Optional — single-node can disable

## Telegram / OpenAI trust assumptions

- Tokens prove identity to third parties
- Outages are availability not integrity attacks (best effort)

## Filesystem trust

- Host disk not multi-tenant hostile
- `OUTPUT_DIR` not world-writable
- SQLite file permissions restrict other users

## Snapshot trust guarantees

- Snapshot is **copy of inspection state at capture time** — not cryptographic proof unless operator stores hashes
- Supplemental integrity report optional

## Evidence trust guarantees

- `verify-runtime` FAIL means do not trust checksums
- WARNING means operator judgment
- Frozen schema v1 only in 1.x line

## Related

- [artifact_integrity.md](artifact_integrity.md) · [compatibility_policy.md](../compatibility_policy.md)
