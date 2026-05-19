from __future__ import annotations

from pathlib import Path

from bot.trust_calibration.agreement import analyze_operator_agreement
from bot.trust_calibration.subsystems import compute_subsystem_metrics
from bot.trust_calibration.types import TrustBand, band_for_scores
from bot.trust_calibration.report import build_trust_calibration
from bot.storage.db import init_database


def test_band_assignment() -> None:
    assert band_for_scores(reliability=0.8, precision=0.7, stability=0.7) == TrustBand.HIGHLY_RELIABLE
    assert band_for_scores(reliability=0.2, precision=0.2, stability=0.3) == TrustBand.LOW_CONFIDENCE


def test_agreement_analysis() -> None:
    rows = [
        {
            "pending_news_id": 1,
            "rating": "bad",
            "trace": {
                "editorial_priority_score": 0.75,
                "editorial_quality": {"warnings": ["weak headline"]},
            },
        },
        {
            "pending_news_id": 2,
            "rating": "good",
            "trace": {
                "editorial_priority_score": 0.8,
                "editorial_quality": {"warnings": ["low information density"]},
            },
        },
    ]
    result = analyze_operator_agreement(rows)
    assert result["totals"]["rated"] == 2
    assert result["totals"]["warning_confirmed"] >= 1
    assert result["totals"]["warning_false_positive"] >= 1


def test_subsystem_metrics_from_agreement() -> None:
    agreement = analyze_operator_agreement(
        [
            {
                "pending_news_id": 1,
                "rating": "bad",
                "trace": {"editorial_quality": {"warnings": ["weak headline"]}},
            },
        ],
    )
    metrics = compute_subsystem_metrics([], agreement)
    assert "editorial_quality" in metrics
    assert metrics["editorial_quality"]["precision"] >= 0


def test_build_calibration_report(tmp_path: Path) -> None:
    db = init_database(tmp_path / "trust.db")
    snap = build_trust_calibration(db)
    assert "subsystems" in snap
    assert "agreement" in snap
    assert "longitudinal" in snap
