# RFC-003: Queue backend abstraction

**Status:** Draft · **Target:** v1.2+ opt-in

## Problem

`worker/job_queue.py` and `worker/reliable_transport.py` assume Redis for multi-worker semantics; memory mode is dev-only and not uniformly abstracted.

## Proposal

```python
# Conceptual — not implemented
class QueueBackend(Protocol):
    async def enqueue(self, kind: JobKind, env: JobEnvelope) -> str: ...
    async def ack(self, kind: JobKind, raw: bytes, *, delivery_id: str | None) -> None: ...
```

- `QUEUE_BACKEND=memory|redis` (default unchanged).
- Factory in `worker/queue_factory.py`; no new job kinds.

## Constraints (ADR-003)

- No in-repo workflow orchestrator or Celery
- No new inspection CLI

## Migration risk

Medium — worker deployments must set backend consistently.
