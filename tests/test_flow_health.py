from __future__ import annotations

from collections import Counter
from pathlib import Path

from bot.editorial.flow_health.adaptive import adaptive_modulation
from bot.editorial.flow_health.funnel import detect_starvation, record_funnel
from bot.editorial.flow_health.quality_zones import (
    QualityZone,
    apply_zone_to_blockers,
    classify_quality_zone,
)
from bot.storage.db import init_database


def test_starvation_detection() -> None:
    s = detect_starvation(
        Counter({"FETCHED": 30, "PUBLISHED": 1, "CLUSTERED": 15}),
        hours=6,
    )
    assert s["detected"] is True
    assert s["reason"] in ("cluster_absorption", "low_publish_throughput", "dedupe_strict")


def test_quality_zones_floor() -> None:
    zone = classify_quality_zone(quality_score=0.5, trust_score=0.6)
    assert zone == QualityZone.LOW_CONFIDENCE
    blockers, z = apply_zone_to_blockers(
        ["quality_low", "trust_low"],
        quality_score=0.5,
        trust_score=0.6,
    )
    assert z == QualityZone.LOW_CONFIDENCE


def test_adaptive_modulation_fail_open() -> None:
    m = adaptive_modulation()
    assert 0.5 <= m["cluster_similarity_threshold"] <= 0.95


def test_funnel_record(tmp_path: Path) -> None:
    db = init_database(tmp_path / "funnel.db")
    import os

    os.environ["PUBLISH_FLOW_HEALTH_ENABLED"] = "true"
    record_funnel("FETCHED")
    record_funnel("PUBLISHED")
