# Maintenance policy (v1.0.0+)

How this repository evolves after the operational freeze.

## Compatibility-first

Patch and minor releases (1.0.x) prioritize **not breaking** operator scripts, Makefile targets, frozen JSON filenames, and inspection CLI commands.

## Additive-only policy (runtime inspection)

Within 1.0.x:

- **Allowed:** optional JSON fields, docs, tests, bug fixes in builders, formatting in governance scope.
- **Not allowed without major version + ADR:** new `runtime/*.json` files, lifecycle reorder, category taxonomy changes, new inspection CLIs.

## Bugfix over expansion

Prefer fixing incorrect validation, checksum logic, or documentation over adding parallel reports or subsystems.

## Operational simplicity

Maintenance work should reduce operator confusion (clearer docs, stable `make` output) — not introduce deployment platforms or control planes.

## Review expectations for new complexity

> **New architectural layers require exceptional justification.**

Proposals must include: problem statement, why existing artifacts/CLIs are insufficient, ADR draft, contract test plan, and explicit non-goals check against [STABILITY_GUARANTEES.md](STABILITY_GUARANTEES.md).

## Release expectations

Before tagging:

```bash
make release-check
```

See [RELEASE_FINALIZATION.md](RELEASE_FINALIZATION.md) and [RELEASE_PROCESS.md](RELEASE_PROCESS.md).

## Related

- [REPRODUCIBILITY.md](REPRODUCIBILITY.md)
- [REPOSITORY_STANDARDS.md](REPOSITORY_STANDARDS.md)
- [architecture/ADR-015-runtime-stabilization-and-contract-freeze.md](architecture/ADR-015-runtime-stabilization-and-contract-freeze.md)
