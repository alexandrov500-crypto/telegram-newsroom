# AI governance (lightweight)

This repo uses a **small, typed prompt registry** and **execution metadata** attached to drafts — not a separate prompt CMS or framework.

## Prompt registry

- `ai/prompt_types.py` — `PromptSpec` (id, version, fingerprint, optional model hints).
- `ai/prompt_registry.py` — `resolve_cluster_draft_prompt(settings)` for cluster JSON drafting.
- `ai/prompts/` — version constants / re-exports.

The **fingerprint** is a SHA-256 of stable settings fields that influence system/user prompts (`summary_style`, `headline_mode`, editorial flags, digest knobs, …). Bump `prompt_version` when prompt *semantics* change even if the fingerprint algorithm stays the same.

## Execution metadata

After a successful OpenAI cluster call, `scheduler/jobs.py` merges `draft_extras["ai_generation"]` with:

| Field | Meaning |
|-------|---------|
| `prompt_id` / `prompt_version` / `prompt_fingerprint` | Governance lineage |
| `model` | Model name used |
| `latency_sec` | Last successful HTTP completion duration |
| `retry_count` | JSON-repair retries consumed in-process |
| `input_tokens` / `output_tokens` / `total_tokens` | From `completion.usage` when present |
| `estimated_cost_usd` | Heuristic from `ai/cost_estimation.py` (not billing truth) |
| `safety_warnings` | Codes from `ai/safety_hooks.py` heuristics |

## Metrics & reports

Counters (see `utils/metrics.py`): `ai_cluster_calls`, `ai_cluster_failures`, `ai_input_tokens`, `ai_output_tokens`, `ai_cost_micro_usd`, plus existing `openai_*`.

- `python -m tools.admin_cli ai-analytics`
- `build_ai_governance_report` is included in `export-runtime-report` JSON bundle.
- `gather_runtime_health` exposes `checks.ai_governance`.

## Safety hooks

`ai/safety_hooks.py` performs **local heuristics** only (empty body, repetition, suspicious HTML substrings). They do **not** block publishing by default; warnings are stored for operators and logs.

## Operational notes

- Token usage depends on the OpenAI client returning `usage`; if absent, cost fields may be `null`.
- Cost table in `ai/cost_estimation.py` is intentionally small; extend per model as you adopt new endpoints.
