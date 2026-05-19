# Event-Sourced Newsroom Pipeline

## Architecture

The newsroom evolves from cluster coordination to **replayable event-driven infrastructure**:

```
ingest → enrich → cluster → signal → digest → approve → publish
         └──────────── sourced_event_log (append-only) ────────────┘
         └──────────── Redis Streams / in-memory stream bus ───────┘
```

### Components

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Envelope | `bot/events/envelope.py` | Canonical v1 event contract |
| Validation | `bot/events/validation.py` | Schema + poison detection |
| Sourced log | `bot/storage/sourced_event_store.py` | Immutable append-only log |
| Stream bus | `bot/distributed/stream/` | Durable delivery, acks, replay |
| Idempotent publish | `bot/publishing/idempotency.py` | Exactly-once-ish Telegram posts |
| Workflows | `bot/workflows/` | Checkpoints, recovery, orchestration |
| Tracing | `bot/observability/tracing.py` | OTEL-ready trace propagation |

## Event envelope (v1)

Required fields: `event_id`, `event_type`, `event_version`, `timestamp`, `payload`, `node_id`.

Operational fields: `causation_id`, `correlation_id`, `partition_key`, `signature`, `retry_count`, `trace_id`, `span_id`.

Legacy `NewsroomEvent` maps via `EventEnvelope.from_legacy_event()` / `to_legacy_event()`.

## Stream backends

| `STREAM_BACKEND` | Behavior |
|------------------|----------|
| `inmemory_stream` (default dev) | Local deque + sourced log |
| `redis_streams` | XADD / XREADGROUP / XACK, retention, DLQ |
| `jetstream` | Stub → in-memory until NATS wired |

Set `EVENT_BUS_BACKEND=redis_streams` or `STREAM_BACKEND=redis_streams`.

## Failure modes

| Failure | Mitigation |
|---------|------------|
| Node crash mid-publish | `publish_receipts` in_progress → retry or dedup on complete |
| Duplicate digest lease holder | Global job lease + workflow checkpoints |
| Handler exception | Retry count → quarantine in sourced log |
| Redis unavailable | Fallback to `inmemory_stream` |
| Replay storm | `correlation_id` timeline + operator replay commands |

## Operator safety

- Poison messages: `retry_count >= 5` → quarantine
- Drain: existing cluster coordinator drain semantics
- Replay: `SourcedEventStore.replay_range()` + `StreamEventBus.replay_stream()`
- Schema: unknown types logged, invalid envelopes rejected

## Production checklist

- [ ] `STREAM_BACKEND=redis_streams` + Redis persistence
- [ ] `CLUSTER_EVENT_SIGNING_KEY` set on all nodes
- [ ] `DATABASE_URL` → PostgreSQL for shared coordination + sourced log (see POSTGRES_UNIFICATION.md)
- [ ] Grafana: `stream_*`, `sourced_events_*`, `workflow_*`, `publish_dedup_*`
- [ ] OpenTelemetry exporter configured (optional `opentelemetry` packages)
- [ ] Rolling upgrade: `NodeCapabilities.envelope_version` within ±1

## Incremental rollout

1. **Phase A** (current): Envelope + sourced log + in-memory stream + publish idempotency
2. **Phase B**: Redis Streams in staging, workflow recovery cron
3. **Phase C**: Emit envelopes from ingest/signal/publish paths
4. **Phase D**: Projections from sourced log (story/digest timelines)
5. **Phase E**: Full PostgreSQL persistence unification
