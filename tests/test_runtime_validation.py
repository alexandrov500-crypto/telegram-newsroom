from __future__ import annotations

from bot.editorial.runtime_validation import runtime_validation_snapshot
from bot.editorial.runtime_validation.digest import verify_digest_silence
from bot.editorial.runtime_validation.persistence import verify_persistence_aging
from bot.editorial.runtime_validation.report import render_validation_summary
from bot.editorial.runtime_validation.scheduler import verify_scheduler_survivability
from bot.editorial.runtime_validation.telemetry import verify_telemetry_stability


def test_persistence_bounded_small_metrics() -> None:
    metrics = {
        "observability_continuity": {"canonical_days": {"2026-05-01": True}},
        "convergence_continuity": {"converged_days": {"2026-05-01": True}},
        "evolution_ledger": {"certification": {"change_count_30d": 1}},
    }
    p = verify_persistence_aging(metrics=metrics)
    assert p["bounded_persistence_ok"] is True
    assert p["persistence_growth_rate"] < 0.5


def test_persistence_flags_oversize() -> None:
    metrics = {"blob": "x" * 300_000}
    p = verify_persistence_aging(metrics=metrics)
    assert p["bounded_persistence_ok"] is False
    assert "metrics_json_oversize" in p["persistence_issues"]


def test_telemetry_fragmentation_nulls() -> None:
    ctx = {
        "flow_governance": {"observability": {"propagation": {"propagation_coherent": False}}},
        "flow_certification": None,
        "flow_closure": None,
        "flow_legacy": None,
        "flow_minimalism": None,
        "flow_doctrine": None,
        "operational_closure_candidate": None,
    }
    t = verify_telemetry_stability(ctx=ctx)
    assert t["collector_integrity_ok"] is False


def test_scheduler_healthy_snapshot() -> None:
    snap = {
        "digest-scheduler": {
            "stalled": False,
            "watchdog_eligible": True,
            "age_sec": 30,
        },
    }
    s = verify_scheduler_survivability(loop_snapshot=snap, pulse={"publish_continuity_ok": True})
    assert s["scheduler_continuity_ok"] is True


def test_digest_silence_minimal_ctx() -> None:
    d = verify_digest_silence(ctx={})
    assert "digest_line_count" in d
    assert d["digest_noise_drift"] >= 0


def test_runtime_validation_report_structure() -> None:
    report = runtime_validation_snapshot(
        metrics={"observability_continuity": {"canonical_days": {}}},
        ctx={"flow_governance": {}},
        loop_snapshot={},
    )
    assert "checks" in report
    assert "summary_lines" in report
    assert report["checks_total"] >= 6


def test_validation_summary_renders() -> None:
    lines = render_validation_summary(
        persistence={"bounded_persistence_ok": True},
        digest={"digest_silence_ok": True},
        scheduler={"scheduler_continuity_ok": True},
        telemetry={"canonical_telemetry_stability": True},
        restart={"restart_survivability_ok": True},
        degradation={"hidden_entropy_observed": False},
        aging={"long_horizon_calm": True},
        overall_ok=True,
    )
    assert any("Persistence" in ln for ln in lines)
    assert len(lines) <= 8
