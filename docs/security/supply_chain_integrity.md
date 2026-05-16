# Supply chain integrity

Dependency trust for production-lite installs.

## Dependency inventory

- Runtime: `requirements.txt` (pinned `==` where policy requires)
- Dev: `requirements-dev.txt`
- Package metadata: `pyproject.toml` (dynamic version from `newsroom._version`)

## Pinned dependency policy

- Direct deps should use `==` pins except documented exceptions (`greenlet`, `redis`, `asyncpg`, `psycopg` ranges).
- Upgrades: [DEPENDENCY_POLICY.md](../DEPENDENCY_POLICY.md) + `make release-check`.

## Hash validation guidance

- Verify PyPI package hashes in controlled environments (pip `--require-hashes` optional operator choice — not mandatory in-repo).
- Record lockfile digest in release notes for maintainers.

## Upgrade verification

1. Read changelog
2. `python3 tools/dependency_audit.py --strict`
3. `make ci-test` + `make release-check`

## Risk notes

| Package | Notes |
|---------|-------|
| `telethon` / `aiogram` | Network-facing; keep updated for security patches |
| `openai` | API client; no secrets in library |
| `redis` | Optional transport |

## Tooling

```bash
python3 tools/dependency_audit.py
python3 tools/dependency_audit.py --strict
```

## Forbidden packages

Maintainers may extend `FORBIDDEN_PACKAGES` in `tools/dependency_audit.py` — typosquat / known-bad names.

## Related

- [DEPENDENCY_POLICY.md](../DEPENDENCY_POLICY.md)
