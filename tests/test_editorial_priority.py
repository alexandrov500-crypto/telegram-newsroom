from __future__ import annotations

from ai.editorial_priority import compute_editorial_priority


def test_priority_high_on_urgency() -> None:
    pri = compute_editorial_priority(
        "BREAKING: major outage",
        [{"channel": "@a", "message_id": 1}, {"channel": "@b", "message_id": 2}, {"channel": "@c", "message_id": 3}],
        duplicate_intel={"severity": "none", "max_similarity_pct": 0.0},
        quality_scores={"coherence": 0.9, "factual_confidence_heuristic": 0.9},
        source_reputation={"@a": {"score": 0.9}},
    )
    assert pri["priority_level"] == "HIGH"
    assert float(pri["numeric_priority_score"]) >= 0.75
    assert "moderation_hint" in pri


def test_priority_respects_duplicates() -> None:
    pri = compute_editorial_priority(
        "minor update",
        [{"channel": "@a", "message_id": 1}],
        duplicate_intel={"severity": "high", "max_similarity_pct": 99.0},
        quality_scores={"coherence": 0.4, "factual_confidence_heuristic": 0.4},
        source_reputation=None,
    )
    assert pri["priority_level"] in {"LOW", "MEDIUM"}
