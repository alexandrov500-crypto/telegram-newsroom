"""Hooks from collector → ops layer (ledger, dedup, reputation, circuit)."""

from __future__ import annotations

import logging
import time
from typing import Any

from ops.pipeline.dedup_engine import DedupEngine, build_ingest_key
from ops.pipeline.ingestion_ledger import IngestionLedger
from ops.pipeline.observability import emit_ops_event
from ops.pipeline.source_circuit import SourceCircuitBreaker
from ops.pipeline.state_machine import NewsState

logger = logging.getLogger(__name__)


def on_raw_post_inserted(
    *,
    runtime_dir: str | None,
    channel_name: str,
    message_id: int,
    text: str,
) -> dict[str, Any]:
    """
    Called after DB insert of a new raw post.
    Returns metadata: news_id, ingest_key, duplicate (if skipped downstream).
    """
    from app.ops.runtime.pipeline_gate import require_processing_or_skip

    if not require_processing_or_skip(component="ingest_hooks"):
        return {
            "news_id": "",
            "ingest_key": "",
            "duplicate": False,
            "gate_blocked": True,
        }

    from app.ops.ledger.event_ledger import event_fingerprint
    from app.ops.ledger.event_ledger import is_duplicate_event as ledger_is_duplicate
    from app.ops.ledger.writer import record_dropped, record_ingested

    fp = event_fingerprint(channel_name, message_id)
    if ledger_is_duplicate(fp):
        record_dropped(
            None,
            channel=channel_name,
            message_id=message_id,
            reason="ledger_duplicate",
            fingerprint=fp,
        )
        return {
            "news_id": fp[:32],
            "ingest_key": fp,
            "duplicate": True,
            "ledger_duplicate": True,
        }

    try:
        from app.ingestion.idempotency import get_idempotency_store

        store = get_idempotency_store()
        if store is not None and not store.try_claim(channel_name, message_id):
            record_dropped(
                None,
                channel=channel_name,
                message_id=message_id,
                reason="idempotency_duplicate",
                fingerprint=fp,
            )
            emit_ops_event(
                "ingest_idempotent_skip",
                runtime_dir=runtime_dir,
                news_id=fp[:32],
                state=NewsState.REJECTED.value,
                decision_reason="idempotent_fingerprint",
                source=channel_name,
            )
            return {
                "news_id": fp[:32],
                "ingest_key": fp,
                "duplicate": True,
                "idempotent": True,
            }
    except Exception as exc:
        logger.warning("ingestion idempotency check failed: %s", exc)

    ingest_key = build_ingest_key(channel_name, message_id, text)
    news_id = ingest_key[:32]
    ledger = IngestionLedger(runtime_dir)
    dedup = DedupEngine(runtime_dir)
    circuit = SourceCircuitBreaker(runtime_dir)

    verdict = dedup.check(source=channel_name, message_id=message_id, text=text)
    if verdict.duplicate:
        record_dropped(
            None,
            channel=channel_name,
            message_id=message_id,
            reason=f"dedup_{verdict.stage}:{verdict.reason}",
            fingerprint=fp,
            news_id=news_id,
        )
        emit_ops_event(
            "ingest_dedup_skip",
            runtime_dir=runtime_dir,
            news_id=news_id,
            state=NewsState.REJECTED.value,
            decision_reason=f"{verdict.stage}:{verdict.reason}",
            matched_key=verdict.matched_key,
        )
        try:
            from utils.source_reputation import record_duplicate_signal_for_channels

            record_duplicate_signal_for_channels([channel_name], runtime_dir=runtime_dir)
        except Exception:
            pass
        ledger.append(
            news_id=news_id,
            from_state=NewsState.NEW,
            to_state=NewsState.REJECTED,
            decision_reason=f"dedup_{verdict.stage}",
            source=channel_name,
            external_message_id=message_id,
            idempotency_key=ingest_key,
        )
        return {"news_id": news_id, "ingest_key": ingest_key, "duplicate": True}

    allowed, circuit_reason = circuit.allow_fetch(channel_name)
    if not allowed:
        ledger.append(
            news_id=news_id,
            from_state=NewsState.NEW,
            to_state=NewsState.REJECTED,
            decision_reason=f"circuit:{circuit_reason}",
            source=channel_name,
            external_message_id=message_id,
            idempotency_key=ingest_key,
        )
        return {"news_id": news_id, "ingest_key": ingest_key, "duplicate": False, "circuit_blocked": True}

    dedup.register(source=channel_name, message_id=message_id, text=text)
    ledger.append(
        news_id=news_id,
        from_state=None,
        to_state=NewsState.NEW,
        decision_reason="ingested",
        source=channel_name,
        external_message_id=message_id,
        idempotency_key=ingest_key,
    )
    ledger.append(
        news_id=news_id,
        from_state=NewsState.NEW,
        to_state=NewsState.VALIDATED,
        decision_reason="schema_ok",
        source=channel_name,
        external_message_id=message_id,
        idempotency_key=ingest_key,
    )
    emit_ops_event(
        "ingest_validated",
        runtime_dir=runtime_dir,
        news_id=news_id,
        state=NewsState.VALIDATED.value,
        source=channel_name,
    )
    try:
        from app.reliability.source_health import record_event

        record_event(runtime_dir, channel_name, ok=True, dedup=False)
    except Exception:
        pass
    try:
        from app.ops.control_plane.guards import ingestion_allowed, should_drop_message
        from app.ops.priority_router import ops_lanes_enabled, schedule_route_message

        if should_drop_message(lane="ingest"):
            record_dropped(
                {
                    "news_id": news_id,
                    "source": channel_name,
                    "channel_name": channel_name,
                    "message_id": message_id,
                    "text": text,
                },
                reason="emergency_halt",
                fingerprint=fp,
            )
            emit_ops_event(
                "ingest_ops_halt_drop",
                runtime_dir=runtime_dir,
                news_id=news_id,
                state=NewsState.REJECTED.value,
                decision_reason="emergency_halt",
            )
            return {"news_id": news_id, "ingest_key": ingest_key, "duplicate": False, "ops_dropped": True}
        if not ingestion_allowed():
            return {"news_id": news_id, "ingest_key": ingest_key, "duplicate": False, "ingestion_paused": True}
        ingested_eid = record_ingested(
            {
                "news_id": news_id,
                "ingest_key": ingest_key,
                "source": channel_name,
                "channel_name": channel_name,
                "message_id": message_id,
                "text": text,
                "runtime_dir": runtime_dir,
            },
            extra={"state": NewsState.VALIDATED.value},
        )
        if ingested_eid is None:
            record_dropped(
                None,
                channel=channel_name,
                message_id=message_id,
                reason="ledger_ingest_race",
                fingerprint=fp,
            )
            return {"news_id": news_id, "ingest_key": ingest_key, "duplicate": True, "ledger_duplicate": True}
        if ops_lanes_enabled():
            schedule_route_message(
                {
                    "news_id": news_id,
                    "ingest_key": ingest_key,
                    "source": channel_name,
                    "channel_name": channel_name,
                    "message_id": message_id,
                    "text": text,
                    "runtime_dir": runtime_dir,
                    "ingested_at_unix": time.time(),
                }
            )
    except Exception as exc:
        logger.warning("ops priority route schedule failed: %s", exc)
    return {"news_id": news_id, "ingest_key": ingest_key, "duplicate": False}
