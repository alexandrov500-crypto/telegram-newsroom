# Live validation runtime flow

Bounded v3 validation against real Telegram runtime conditions. CI exercises mocked paths; live paths are opt-in via `TELEGRAM_LIVE_VALIDATE=1`.

## Validation flow (operator + CI)

```mermaid
flowchart TD
    A[make live-validation-validate] --> B{pytest tests/live}
    B -->|default| C[Mocked session / floodwait / integrity / recovery]
    B -->|TELEGRAM_LIVE_VALIDATE=1| D[Optional live connect test]
    A --> E[live_telegram_diagnostics.py]
    E --> F[Read metrics + worker retry burst]
    F --> G{findings?}
    G -->|HIGH| H[Stop live validation]
    G -->|OK/WARNING| I[Operator checklist]
    I --> J[Staging channel ≤5 publishes]
```

## Publish lifecycle

```mermaid
sequenceDiagram
    participant Op as Operator / Worker
    participant PS as publish_service
    participant Lock as publish_draft_lock
    participant DB as SQLite
    participant TG as Telegram API

    Op->>PS: execute_admin_publication_flow
    PS->>PS: idempotency_key check
    PS->>Lock: acquire draft_id
    alt lock contended
        Lock-->>PS: false
        PS-->>Op: ALREADY_HANDLED
    end
    PS->>DB: approve + publishing
    PS->>TG: publish_draft_to_channel chunks
    loop each chunk
        TG-->>PS: message_id or error
    end
    PS->>DB: mark_draft_published
    alt finalize fail
        PS-->>Op: FINALIZE_MISMATCH
    else ok
        PS-->>Op: OK + channel_message_id
    end
    Lock->>Lock: release Redis key
```

## Retry lifecycle

```mermaid
flowchart LR
    subgraph Collector
        C1[with_telethon_retries] --> C2{FloodWait?}
        C2 -->|yes| C3[sleep max sec, attempt]
        C2 -->|RPC/OS| C4[exp backoff cap 30s]
        C2 -->|SessionPassword| C5[terminal raise]
    end
    subgraph Publisher
        P1[async_retry per chunk] --> P2{success?}
        P2 -->|no| P3[sleep 0.6s]
        P3 --> P1
        P2 -->|yes| P4[next chunk]
    end
```

## Worker recovery lifecycle

```mermaid
flowchart TD
    W[Worker handles job] --> F{failure}
    F -->|transient + WORKER_RETRY_SAFE| R[re-enqueue then ack]
    F -->|terminal| D[DLQ / fail per policy]
    R --> Q[Queue delay]
    Q --> W
    S[Process restart] --> L[Publish lock TTL or release]
    L --> W
```

## Redis locking model

```mermaid
flowchart TD
    Start[publish_draft_lock] --> Redis{Redis available?}
    Redis -->|no + strict| Deny[yield False STRICT_DENIED]
    Redis -->|no + loose| Local[asyncio.Lock per draft_id]
    Redis -->|yes| NX[SET key NX EX ttl]
    NX -->|ok| Hold[Publish work]
    NX -->|fail| Contend[yield False CONTENTION]
    Hold --> Del[DELETE key in finally]
    Redis -->|error + strict| Deny
    Redis -->|error + loose| Fallback[redis_fallback → local lock]
```

## Operator workflow boundaries

| Activity | CI / automated | Operator manual |
|----------|----------------|-----------------|
| Telethon reconnect semantics | Mocked tests | 24h session watch |
| Real channel publish | Not in default CI | Staging ≤5 posts |
| DLQ triage | Not automated | Checklist in operator_workflow_validation.md |
| Moderation fatigue | N/A | Sign-off |
| Diagnostics | `live_telegram_diagnostics` | Interpret findings |
| Governance stop | Contract tests | Abort on HIGH findings |

## Boundaries (explicit non-goals)

- No mass production rollout in this phase
- No uncontrolled load / spam patterns
- No changes to frozen `runtime/*.json` contracts
- No mandatory live Telegram in `make ci-test`

## References

- [../live_validation/live_telegram_validation_plan.md](../live_validation/live_telegram_validation_plan.md)
- [../operations/retry_error_matrix.md](../operations/retry_error_matrix.md)
- [../operations/publish_idempotency.md](../operations/publish_idempotency.md)
- ADR-029 live Telegram operational validation
