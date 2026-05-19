# Platform Ecosystem Layer

Transforms the mature autonomous newsroom into a **reusable media operations platform** with safe extensibility, orchestration primitives, and internal developer tooling.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Platform Coordinator                      │
├──────────┬──────────┬──────────┬──────────┬───────────────┤
│ Plugins  │ Workflows│  Graph   │ Cognition│ Policy Engine │
├──────────┴──────────┴──────────┴──────────┴───────────────┤
│ IDP Inventory │ Internal Gateway │ Observability Hub        │
│ Platform Governance │ SDK Helpers                             │
└─────────────────────────────────────────────────────────────┘
         │ composes with ops_evolution, ga_ops, live_ops
```

## Enable

```bash
PLATFORM_ENABLED=true
# or inherits OPS_EVOLUTION_ENABLED=true
```

Sub-features: `PLATFORM_PLUGINS`, `PLATFORM_WORKFLOWS`, `PLATFORM_GRAPH`, `PLATFORM_POLICY`, `PLATFORM_OBS_HUB`, `PLATFORM_GATEWAY`, `PLATFORM_GOVERNANCE`.

## Components

| Area | Package | Purpose |
|------|---------|---------|
| Plugin system | `bot/platform/plugins/` | Typed manifests, sandboxes, registry, audit |
| IDP | `bot/platform/idp/` | Service inventory, dependency maps, event schemas |
| Workflows | `bot/platform/workflow/` | Declarative defs; integrates `workflow_runs` |
| Knowledge graph | `bot/platform/graph/` | Story/source/incident/risk edges |
| Multi-agent cognition | `bot/platform/cognition/` | Debate, consensus, agent metrics |
| Policy engine | `bot/platform/policy/` | Rollout, publish, budget, moderation policies |
| Observability hub | `bot/platform/observability/` | Unified platform snapshots |
| Internal gateway | `bot/platform/gateway/` | Scoped APIs, rate limits, audit |
| Governance | `bot/platform/governance/` | Ecosystem risk, trust scoring |
| SDK | `bot/platform/sdk/` | `invoke_internal`, `policy_simulate` |

## Telegram commands

| Command | Description |
|---------|-------------|
| `/plugins_live` | Active plugins by category |
| `/plugin_health` | Health and trust scores |
| `/platform_inventory` | Architecture inventory |
| `/dependency_graph` | Service dependencies |
| `/workflow_live` | Workflow run summary |
| `/workflow_trace <id>` | Checkpoint trace |
| `/graph_insights` | Graph neighbors |
| `/risk_relations` | Risk edge aggregates |
| `/agent_mesh` | Agent specialization metrics |
| `/debate_trace <story_id>` | Editorial debate trace |
| `/policy_status` | Active policies and drift |
| `/policy_diff [kind]` | Policy version diff |
| `/platform_health` | Unified health snapshot |
| `/topology_snapshot` | Platform topology |
| `/ecosystem_risk` | Ecosystem risk score |
| `/governance_audit` | Governance export summary |

## HTTP

`GET /platform` — platform tick + snapshot (health server).

## Database tables

- `platform_plugins`, `platform_plugin_audit`
- `platform_workflow_defs`
- `platform_graph_edges`
- `platform_policies`
- `platform_api_audit`
- `platform_inventory`

Reuses existing `workflow_runs`, `workflow_checkpoints`.

## Integration

Installed in `bot/main.py` after ops evolution. Ops tick ingests failure issues into the knowledge graph and refreshes observability snapshots.
