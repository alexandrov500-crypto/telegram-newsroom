# Editorial policy (per-channel, explainable)

Policies tune **relevance adjustments**, **suppress thresholds**, **cadence / quiet hours**, and **saturation sensitivity** without ML or vector search.

## Storage & configuration

| Source | Purpose |
|--------|---------|
| `RUNTIME_STATE_DIR/editorial_policies.json` | Versioned JSON: `default` partial object + `channels` map (keys = normalized channel names) |
| `EDITORIAL_POLICIES_JSON` | Optional env overlay (merged on top of file) |
| `Settings.editorial_policies_json` | Same string as env, loaded in `app.config` |

Loader: `editorial/policy.py` → `load_editorial_policy_bundle`, `resolve_effective_policy`, `dominant_channel_key`.

Models: `editorial/policy_models.py` → `ChannelEditorialPolicy`, `EditorialPolicyBundle`, `merge_policies`.

## Policy-aware relevance

`editorial/relevance.py` computes base `RelevanceBreakdown`, then `apply_editorial_policy_to_relevance` mutates:

- `policy_delta`, `policy_notes`, `policy_adjustments` (string-keyed deltas),
- `total` clamped to `[0, 100]`.

Signals include preferred/avoided substrings, low source diversity, stale topic memory, oversaturation multiplier, optional entity token boosts, evergreen-update tone penalty.

## Adaptive thresholds

`editorial/adaptation.py` → `adaptive_threshold_overrides(feedback_stats, policy)` returns adjusted `relevance_suppress_below`, `relevance_cooldown_update_below`, `duplicate_signal_suppress_above` plus `notes`. Used by `editorial/pipeline_decision.py` for suppress rules.

## CLI

```bash
python3 -m tools.admin_cli policy-debug
python3 -m tools.admin_cli policy-debug --channel wire_a --json
```

Global `--json` must appear **before** the subcommand when used.

## Tests

See `tests/test_editorial_policy_cadence.py`.
