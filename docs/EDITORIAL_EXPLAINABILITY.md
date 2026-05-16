# Editorial explainability

Editors reason about drafts using **Telegram commands**, **inline buttons**, and optional **ops HTTP pages** — no separate SPA.

## Rendering layer

`editorial/explanations.py`:

- `explain_from_draft_extras` — concise + detailed + structured dict + HTML-safe fragments
- `explain_suppression` — human list of pipeline / gate reasons
- `explain_cadence_block` — cadence quiet-hours / burst reasons
- `explain_escalation` / `explain_confidence_summary` — short prose helpers

Inputs are **`draft_extras` JSON** produced by the pipeline (`cluster_intelligence.pipeline_decision`, confidence, publication intel).

## Textual diff

`editorial/diffing.py`:

- `unified_text_diff` — small unified diff
- `headline_and_lead_diff` — compares editor title/summary vs first lines of body (heuristic)
- `ai_vs_editor_body_diff` — optional AI snapshot vs current body
- `format_edit_history` — renders `Draft.edit_history` moderation trail

`merge_draft_extras` records short previews into `edit_history` when `moderation_note` or `policy_override_reason` is set (`db/repository.py`).

## Bot ergonomics

- `/explain <id>`, `/diff <id>` — full text helpers
- Inline **Explain** / **Diff** buttons on draft keyboards (`bot/keyboards.py`)
- `/note <id> <text>` — stores `moderation_note` in `draft_extras`
- `/policy_override <id> <reason>` — stores `policy_override_reason`
- `/find topic:… entity:… fingerprint:… suppression:… status:…` — operational search (`search_drafts_operational`)

## Ops pages

See `docs/WEB_ADMIN.md` for URL patterns mirroring explain/trace flows in HTML.
