# Unsupported deployment registry

Honest list of what the project **does not** support operationally.

## Unsupported scaling models

- Horizontal multi-node app tier with shared SQLite
- Active-active multi-region publish
- Auto-scaling worker pools without Redis discipline
- Read replicas for write path without migration program
- Sharded job queues across clusters (in-repo)

## Dangerous deployment patterns

- NFS or cloud sync folder for `DATABASE_URL` sqlite file
- Multiple `app.main` instances writing one DB
- Workers > CPU cores “because queue is long” during retry storm
- `PUBLISH_LOCK_STRICT=0` with `WORKER_COUNT>1`
- Unbounded `OUTPUT_DIR` on small disks

## Anti-patterns

- “Works in dev” load test → production capacity claim
- Disabling DLQ to “reduce noise”
- Increasing retry limits instead of fixing root cause
- Skipping nightly inspection to save disk
- Running chaos tests in production

## Deceptive “works in dev” setups

- Single-process laptop with no Redis handling 10x prod rate
- Empty `OUTPUT_DIR` restore in seconds → prod restore with GB of evidence
- In-memory queue with no crash recovery testing
- SQLite on fast SSD vs prod on saturated disk

## Unsupported HA claims

- Kubernetes pod restart = HA for editorial publish
- Two replicas without distributed lock + single DB writer
- Load balancer in front of SQLite writers

## Unsupported distributed patterns

- Microservice split (ingest / publish / inspect as separate deployables) without new ADR
- Mandatory Kafka/NATS migration
- Service mesh sidecars as requirement
- Cloud orchestration layer replacing operator runbooks

## What is supported instead

See [operational_topologies.md](operational_topologies.md) T0–T3 and [capacity_planning.md](capacity_planning.md).
