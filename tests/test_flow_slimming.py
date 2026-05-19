from __future__ import annotations

from bot.editorial.flow_health.slimming.config_surface import analyze_config_surface
from bot.editorial.flow_health.slimming.consolidation import analyze_heuristic_consolidation
from bot.editorial.flow_health.slimming.operational_core import operational_core_map
from bot.editorial.flow_health.slimming.snapshot import slimming_snapshot
from bot.editorial.flow_health.slimming.telemetry_prune import prune_cockpit_bullets


def test_config_complexity_bounded() -> None:
    c = analyze_config_surface()
    assert 0.0 <= c["config_complexity_score"] <= 1.0


def test_consolidation_candidates() -> None:
    r = analyze_heuristic_consolidation(adaptive={"starvation_active": False, "relaxation": {}})
    assert r["consolidation_candidates"]


def test_prune_stable_bullets() -> None:
    ctx = {"publish_funnel": {"starvation": {"detected": False}}, "flow_governance": {}}
    bullets = ["Configuration pressure low", "Starvation active"]
    out = prune_cockpit_bullets(bullets, ctx)
    assert "Configuration pressure low" not in (out.get("bullets") or [])


def test_operational_core_map() -> None:
    m = operational_core_map()
    assert m["core"] and m["advisory"]


def test_slimming_snapshot_shape() -> None:
    s = slimming_snapshot()
    assert "consolidation" in s and "change_risk" in s
