from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.cognitive.runtime import build_cognitive_runtime
from bot.epistemic.confidence import ConfidenceInputs, ConfidenceModel
from bot.epistemic.contradiction import ContradictionGraph
from bot.epistemic.drift import DriftAnalyzer
from bot.epistemic.governance import EpistemicGovernance
from bot.epistemic.misinformation import MisinformationDetector, PropagationSignal
from bot.epistemic.narrative import NarrativeTracker
from bot.epistemic.replay import EpistemicReplayValidator
from bot.epistemic.repository import EpistemicRepository
from bot.epistemic.runtime import build_epistemic_integrity_layer
from bot.epistemic.trust import TrustGraph
from bot.mesh.runtime import build_federated_cognitive_mesh
from bot.storage.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "epistemic.db")


def test_confidence_model_bounded(db_path: Path) -> None:
    repo = EpistemicRepository(db_path)
    model = ConfidenceModel(repo)
    s1 = model.score("story", "1", ConfidenceInputs(base_score=0.9, evidence_count=1))
    s2 = model.score(
        "story",
        "1",
        ConfidenceInputs(base_score=0.99, evidence_count=1, prior_confidence=s1.confidence),
    )
    assert s2.confidence <= s1.confidence + 0.16
    assert s2.uncertainty >= 0.05


def test_contradiction_detection(db_path: Path) -> None:
    graph = ContradictionGraph(EpistemicRepository(db_path))
    record = graph.detect_pair(
        subject_type="story",
        subject_id="42",
        claim_a="Attack confirmed by officials",
        claim_b="No attack occurred officials say",
        region_a="eu",
        region_b="us",
        score_a=0.8,
        score_b=0.3,
    )
    assert record is not None
    assert record.minority_views


def test_narrative_framing(db_path: Path) -> None:
    tracker = NarrativeTracker(EpistemicRepository(db_path))
    fp = tracker.track(
        topic="ukraine",
        title="BREAKING: urgent ceasefire talks",
        summary="Exclusive revealed escalation",
        source_count=1,
    )
    assert "urgency" in fp.framing_tags or "sensational" in fp.framing_tags


def test_trust_reversible(db_path: Path) -> None:
    repo = EpistemicRepository(db_path)
    trust = TrustGraph(repo)
    edge = trust.update_from_contradiction("reuters", contradiction_count=3)
    assert edge.reversible
    restored = trust._decay.restore("mesh:local", "source:reuters", operator_id="op", reason="test")
    assert restored >= edge.trust_score


def test_misinformation_detector(db_path: Path) -> None:
    det = MisinformationDetector(EpistemicRepository(db_path), node_id="n1", region="eu")
    alert = det.analyze(
        "story:99",
        PropagationSignal(
            source_count=1,
            burst_rate=8.0,
            diversity_score=0.1,
            narrative_anomaly=0.7,
            replay_seen=True,
        ),
    )
    assert alert is not None
    assert alert.requires_review


def test_epistemic_replay(db_path: Path) -> None:
    repo = EpistemicRepository(db_path)
    model = ConfidenceModel(repo)
    validator = EpistemicReplayValidator(repo, model)
    result = validator.validate_consensus(
        "sess1",
        original_votes=[0.7, 0.75, 0.72],
        replay_votes=[0.71, 0.74, 0.73],
    )
    assert result.passed
    assert result.stability_score > 0.8


def test_drift_analyzer(db_path: Path) -> None:
    drift = DriftAnalyzer(EpistemicRepository(db_path))
    report = drift.analyze_consensus_homogenization([0.9, 0.91, 0.9, 0.92, 0.91, 0.9])
    assert report.drift_kind == "consensus_homogenization"


def test_epistemic_governance(db_path: Path) -> None:
    repo = EpistemicRepository(db_path)
    gov = EpistemicGovernance(repo)
    from bot.epistemic.confidence import ConfidenceModel

    model = ConfidenceModel(repo)
    score = model.score("x", "1", ConfidenceInputs(base_score=0.99, evidence_count=0))
    decision = gov.validate_score(score)
    assert not decision.allowed or score.confidence <= 0.95


def test_epistemic_integrity_tick(db_path: Path) -> None:
    cognitive = build_cognitive_runtime(db_path, node_id="n1", node_region="eu")
    mesh = build_federated_cognitive_mesh(db_path, cognitive, node_id="n1", region="eu")
    layer = build_epistemic_integrity_layer(
        db_path, cognitive, mesh=mesh, node_id="n1", region="eu",
    )

    async def _run():
        report = await layer.tick(mesh_health=0.9, queue_backlog=100)
        assert "federation_stability" in report

    asyncio.run(_run())


def test_analyze_story(db_path: Path) -> None:
    cognitive = build_cognitive_runtime(db_path, node_id="n1", node_region="eu")
    layer = build_epistemic_integrity_layer(
        db_path, cognitive, node_id="n1", region="eu",
    )

    async def _run():
        result = await layer.analyze_story(
            story_id=1,
            title="Test headline for epistemic analysis",
            summary="Summary with enough detail for scoring.",
            source="test",
            source_count=2,
        )
        assert result.get("narrative") or result.get("epistemic_score")

    asyncio.run(_run())
