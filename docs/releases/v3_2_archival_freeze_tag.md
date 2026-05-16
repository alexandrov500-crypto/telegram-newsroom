# v3.2 archival freeze tag

Recommended tag after archival closure commit and `make archival-freeze-validate` green.

## Tag name

```
v3.2-archival-baseline
```

## When to apply

1. All stewardship + immutable + archival closure files committed
2. `make archival-freeze-validate` passes
3. `git status` clean

## Annotated tag command

```bash
git tag -a v3.2-archival-baseline -m "$(cat <<'EOF'
v3.2 archival baseline

Immutable stewardship certification complete (ADR-036).
Archival-grade preservation achieved: fingerprint, archive bundle,
integrity seal, publication manifest.

Repository governance finalized for offline ops tooling.
Runtime/tooling separation permanent.

Future evolution requires explicit governance restart (ADR-037+).
Do not move v3.2-operational-tooling-freeze.

Verify: make archival-freeze-validate
EOF
)"
```

## Relationship to tooling freeze tag

| Tag | Role |
|-----|------|
| `v3.2-operational-tooling-freeze` | Immutable **tooling** code baseline (`ab7c92a`) |
| `v3.2-archival-baseline` | **Publication** of governance + archival artifacts |

Do not delete or retag `v3.2-operational-tooling-freeze`.

## Push

```bash
git push origin v3.2-archival-baseline
```
