"""Production ops layer: ledger, dedup, state machine, reputation, circuit breaker, checkpoint."""

from ops.pipeline.checkpoint_store import load_checkpoint, save_checkpoint
from ops.pipeline.dedup_engine import DedupEngine
from ops.pipeline.ingestion_ledger import IngestionLedger
from ops.pipeline.observability import emit_ops_event
from ops.pipeline.source_circuit import SourceCircuitBreaker
from ops.pipeline.state_machine import NewsState, transition_allowed

__all__ = [
    "DedupEngine",
    "IngestionLedger",
    "NewsState",
    "SourceCircuitBreaker",
    "emit_ops_event",
    "load_checkpoint",
    "save_checkpoint",
    "transition_allowed",
]
