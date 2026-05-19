from __future__ import annotations

from pathlib import Path

from bot.ops_evidence.confidence import compute_operational_confidence
from bot.ops_evidence.noise import detect_retirement_candidates
from bot.ops_evidence.report import build_weekly_operational_review, week_id_for
from bot.ops_evidence.repository import EvidenceReviewRepository
from bot.ops_evidence.signals import rank_signal_effectiveness
from bot.ops_evidence.timeline import build_reliability_timeline
from bot.ops_evidence.types import ConfidenceBand, RetirementLabel
from bot.storage.db import init_database
from bot.trust_calibration.agreement import analyze_operator_agreement


def test_week_id_format() -> None:
    wid = week_id_for()
    assert "-W" in wid


def test_signal_ranking() -> None:
    events = [
        {
            "subsystem": "editorial_quality",
            "signal_type": "quality_warning",
            "operator_action": "ignored",
            "outcome": "false_positive",
        },
        {
            "subsystem": "editorial_quality",
            "signal_type": "quality_warning",
            "operator_action": "confirmed",
            "outcome": "true_positive",
        },
    ]
    agreement = analyze_operator_agreement([])
    ranked = rank_signal_effectiveness(events, agreement)
    assert ranked
    assert ranked[0]["signal"] == "editorial_quality:quality_warning"


def test_retirement_candidates() -> None:
    rankings = [
        {
            "signal": "fatigue_detection:fatigue_warning",
            "subsystem": "fatigue_detection",
            "precision": 0.2,
            "ignore_ratio": 0.8,
            "emitted": 10,
        },
    ]
    subs = {"fatigue_detection": {"ignored_ratio": 0.7, "precision": 0.25, "event_count": 10}}
    cands = detect_retirement_candidates(rankings, subs, {"suppressed": 10, "delivered": 2})
    assert any(c["label"] == RetirementLabel.CANDIDATE_FOR_REMOVAL.value for c in cands)


def test_confidence_index() -> None:
    conf = compute_operational_confidence(
        runtime={"pulse": {"event_loop_lag_max": 0.1, "stalled_loop_events": 0}},
        publish_stats={"success_rate": 0.9},
        trust_snapshot={"subsystems": {"editorial_quality": {"reliability": 0.8}}},
        agreement={"totals": {"rated": 5, "good": 4}},
        incident_count=0,
        timeline_direction="improving",
    )
    assert conf["band"] in {b.value for b in ConfidenceBand}
    assert conf["score"] > 0.5


def test_reliability_timeline() -> None:
    hist = [
        {"date": "2026-05-10", "subsystem": "editorial_quality", "metrics": {"reliability": 0.6}},
        {"date": "2026-05-11", "subsystem": "editorial_quality", "metrics": {"reliability": 0.7}},
    ]
    tl = build_reliability_timeline(hist, windows=(7,))
    assert "7d" in tl["windows"]


def test_build_weekly_review_persists(tmp_path: Path) -> None:
    db = init_database(tmp_path / "evidence.db")
    review = build_weekly_operational_review(db, persist=True)
    assert "operational_confidence" in review
    assert "signal_effectiveness" in review
    repo = EvidenceReviewRepository(db)
    loaded = repo.load_review(review["week_id"])
    assert loaded is not None
