from __future__ import annotations

from bot.editorial.flow_health.freeze_registry.classifier import classify_subsystem
from bot.editorial.flow_health.freeze_registry.digest import should_ultra_quiet_digest
from bot.editorial.flow_health.freeze_registry.exposure import (
    compute_drift_exposure_index,
    estimate_stewardship_horizon,
)
from bot.editorial.flow_health.freeze_registry.registry import build_freeze_registry
from bot.editorial.flow_health.freeze_registry import freeze_registry_snapshot


def test_classify_immutable_core() -> None:
    assert classify_subsystem("publish_guard") == "IMMUTABLE_CORE"


def test_freeze_registry_shape() -> None:
    reg = build_freeze_registry()
    assert "immutable_core" in reg and reg["experimental_surface_ratio"] >= 0


def test_drift_exposure_bands() -> None:
    d = compute_drift_exposure_index(registry=build_freeze_registry())
    assert d["drift_exposure_band"] in ("MINIMAL", "CONTROLLED", "ELEVATED", "FRAGILE")
    assert 0 <= d["drift_exposure_index"] <= 1


def test_stewardship_horizon() -> None:
    h = estimate_stewardship_horizon()
    assert h["stewardship_horizon_band"] in ("SHORT", "STABLE", "LONG", "AUTONOMOUS_CANDIDATE")
    assert h["stewardship_horizon_days"] >= 1


def test_ultra_quiet_gate() -> None:
    assert should_ultra_quiet_digest(
        certification={
            "operational_confidence": {"operational_confidence_band": "CERTIFIED"},
            "change_pressure": {"change_pressure_band": "LOW"},
        },
        drift_exposure={"drift_exposure_band": "MINIMAL"},
        horizon={"stewardship_horizon_band": "LONG"},
        all_calm=True,
    )


def test_freeze_registry_snapshot() -> None:
    snap = freeze_registry_snapshot()
    assert "evolution_ledger" in snap and "drift_exposure" in snap
