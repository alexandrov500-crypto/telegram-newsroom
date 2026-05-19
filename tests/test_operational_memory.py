from __future__ import annotations

import asyncio
from pathlib import Path

from bot.operational_memory.drift.monitor import DriftMonitor
from bot.operational_memory.factory import build_opmem_stack
from bot.operational_memory.fingerprints.engine import FingerprintEngine
from bot.operational_memory.memory_store.incidents import IncidentMemoryStore
from bot.operational_memory.prediction.engine import PredictiveRiskEngine
from bot.operational_memory.repository import OperationalMemoryRepository
from bot.storage.db import init_database


def test_incident_append(tmp_path: Path) -> None:
    init_database(tmp_path / "op1.db")
    repo = OperationalMemoryRepository(tmp_path / "op1.db")
    store = IncidentMemoryStore(repo)
    iid = store.record("queue_spike", severity="warning", signals={"queue_depth": 200})
    rows = repo.list_incidents(limit=5)
    assert rows[0]["incident_id"] == iid


def test_fingerprint_recurrence(tmp_path: Path) -> None:
    init_database(tmp_path / "op2.db")
    repo = OperationalMemoryRepository(tmp_path / "op2.db")
    engine = FingerprintEngine(repo)
    sig = {"queue_depth": 180, "retry_amplification": 0.2}
    engine.register_from_incident(
        incident_type="queue_spike",
        signals=sig,
        impact=0.5,
        recovery_sec=120.0,
    )
    engine.register_from_incident(
        incident_type="queue_spike",
        signals=sig,
        impact=0.6,
        recovery_sec=90.0,
    )
    fps = repo.list_fingerprints(limit=1)
    assert fps[0]["recurrence_count"] >= 2


def test_predictive_horizons(tmp_path: Path) -> None:
    init_database(tmp_path / "op3.db")
    repo = OperationalMemoryRepository(tmp_path / "op3.db")
    pred = PredictiveRiskEngine(repo)
    out = pred.forecast_all({"stabilization_risk": 0.5, "queue_depth": 100})
    assert "15m" in out
    assert "24h" in out
    latest = repo.latest_predictions()
    assert "15m" in latest


def test_drift_systemic(tmp_path: Path) -> None:
    init_database(tmp_path / "op4.db")
    repo = OperationalMemoryRepository(tmp_path / "op4.db")
    drift = DriftMonitor(repo)
    sig = {"audience_fatigue": 0.2}
    for v in (0.25, 0.3, 0.35, 0.4, 0.45, 0.5):
        sig["audience_fatigue"] = v
        drift.evaluate(sig)
    rows = repo.latest_drift()
    audience = next((r for r in rows if r["domain"] == "audience"), None)
    assert audience is not None


def test_coordinator_tick(tmp_path: Path) -> None:
    async def _run() -> None:
        init_database(tmp_path / "op5.db")
        coord = build_opmem_stack(tmp_path / "op5.db")
        await coord.startup()
        t = await coord.tick(
            signals={
                "queue_depth": 200,
                "stabilization_risk": 0.7,
                "survivability_score": 0.6,
            },
        )
        assert "predictions" in t

    asyncio.run(_run())


def test_recurrent_types(tmp_path: Path) -> None:
    init_database(tmp_path / "op6.db")
    repo = OperationalMemoryRepository(tmp_path / "op6.db")
    store = IncidentMemoryStore(repo)
    store.record("retry_storm", severity="high", signals={"queue_depth": 10})
    store.record("retry_storm", severity="high", signals={"queue_depth": 12})
    rec = repo.recurrent_types(min_count=2)
    assert any(r["incident_type"] == "retry_storm" for r in rec)
