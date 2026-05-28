# Editorial operations — operator feedback

## Feedback actions (advisory)

Recorded in `operator_feedback` table; applied side-effects are **non-bypass**:

| Action | Effect |
|--------|--------|
| `approve` | Logged hint only (publish still via gates) |
| `reject` | Source reputation reject signal |
| `suppress_source` | Operator source block |
| `trusted_source` | Source boost |
| `prioritize_topic` / `deprioritize_topic` | Topic boost / mute |
| `duplicate_mark` | Duplicate signal on sources |
| `false_positive_mark` | Logged |
| `retry` | Hint only — no auto-publish |

## Audit events

- `operator_feedback_received`
- `operator_feedback_applied`
- `operator_feedback_rejected`

## Telegram commands

Existing: `/queue`, `/draft`, `/reject`, `/approve`, `/mute_source`, `/boost_source`

Ops layer: `/runtime`, `/anomalies`, `/lastpub`, `/pause_autopublish`, `/resume_autopublish`

Launch dashboard: `/release_status`, `/burnin_status`, `/go_status`, `/continuity`, `/runtime_state`, `/last_alerts`, `/recent_failures`

`/health` and `/queue` remain on admin router.

## Workflow

1. Review draft in moderation chat  
2. `/reject <id>` or `/approve <id>` (approve = explicit publish, still gated)  
3. For sources: `/mute_source @channel 60` or feedback via future reaction hooks  
4. Check `/runtime` if quality drifts  

Feedback never overrides `execution_graph` or `evaluate_publish_gate`.

## Incident response (editorial)

1. Pause auto if quality drops: `/pause_autopublish`  
2. Suppress bad sources: `/mute_source @channel 1440` or `suppress_source` feedback  
3. Resume when stable: `/resume_autopublish` (gates still apply)  
4. Full ops flow: [OPERATIONS.md](./OPERATIONS.md#incident-response-workflow)
