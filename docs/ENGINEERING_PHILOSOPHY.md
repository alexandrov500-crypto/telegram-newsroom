# Engineering philosophy

Rationale for how this codebase is structured — not marketing copy. Assumes **production-lite**, single-node realism.

## Bounded state

Runtime memory on disk is intentionally capped: latest-only artifacts, bounded qualification history (20 entries), retention policies at DB and filesystem layers. Unbounded growth is treated as an operational defect, not a scaling strategy.

**Implication:** operators prune and snapshot; the system does not accumulate an observability data lake.

## Deterministic artifacts

Offline JSON uses stable key order, `schema_version: 1`, and reproducible checksums in manifests. Tests assert ordering and contracts so refactors cannot silently reshape operator tooling.

**Implication:** diffs and CI comparisons are meaningful without normalizing JSON in ad hoc scripts.

## Shell-first tooling

Make targets and bash scripts wrap Python CLIs. No workflow engine interprets graphs; `runtime_ops.py` calls modules in a fixed sequence.

**Implication:** debugging is `strace`, logs, and reading JSON — not querying a orchestrator API.

## Single-node operational model

SQLite-first, one writer, optional Redis/Postgres documented as scaling paths — not defaults. Capability and policy artifacts describe **single-node** assumptions explicitly.

**Implication:** multi-region HA is out of scope for in-repo tooling.

## Cognitive compactness

Few artifact types, few CLI verbs, one index file as catalog. New engineers should hold the mental model in working memory after one pass through [ARCHITECTURE_MAP.md](ARCHITECTURE_MAP.md).

**Implication:** feature requests that add parallel inspection surfaces face a high bar.

## Inspection over orchestration

Policies and reports **describe** guardrails; they do not enforce them via daemons or admission controllers. Validation runs when invoked (`make verify-runtime`, `--strict`).

**Implication:** compliance is procedural (release checklist), not autonomous.

## Production-lite philosophy

Optimize for a small team operating one deployment: understandable failures, copy-paste CLI, minimal moving parts. Defer platform-scale extensibility unless requirements prove it necessary.

**Implication:** no in-repo Prometheus/Grafana/Kubernetes as first-class citizens.

## Stabilization over expansion

After ADR-014/015, work shifts to packaging, docs, and contract tests — not new governance layers. Complexity growth requires exceptional justification (see [CONTRIBUTING.md](CONTRIBUTING.md)).

**Implication:** proposals for new `runtime/*.json` types should be rejected by default.

## Complexity growth rule

> Complexity growth requires exceptional justification.

Prefer extending existing artifacts with optional fields (schema v1 additive rules) over new filenames, categories, or CLIs.

## Related

- [FAQ.md](FAQ.md) — concise answers to common “why not X?” questions  
- [architecture/RUNTIME_MATURITY.md](architecture/RUNTIME_MATURITY.md) — maturity scope and non-goals  
- [architecture/ADR-003-no-orchestration-policy.md](architecture/ADR-003-no-orchestration-policy.md)
