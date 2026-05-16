from __future__ import annotations

from editorial.explanations import (
    explain_cadence_block,
    explain_confidence_summary,
    explain_escalation,
    explain_from_draft_extras,
    explain_suppression,
)


def test_explain_from_draft_extras_minimal() -> None:
    out = explain_from_draft_extras({})
    assert "concise" in out and "structured" in out
    assert "No cluster intelligence" in out["concise"]


def test_explain_from_draft_extras_with_pipeline() -> None:
    extras = {
        "cluster_intelligence": {
            "pipeline_decision": {
                "relevance": {"total": 42.0, "policy_notes": ["note_a"], "freshness": 1.0},
                "editorial_pipeline": {"outcome": "allow", "reasons": ["r1"]},
                "escalate_priority": True,
                "hold_for_review": False,
            }
        },
        "editorial_escalate": True,
        "editorial_confidence": {"confidence_score": 0.8, "publication_risk_score": 0.1},
    }
    out = explain_from_draft_extras(extras)
    assert "42" in out["concise"]
    assert out["structured"]["escalation"] is True


def test_explain_suppression_and_cadence() -> None:
    assert "No explicit" in explain_suppression({})
    assert "quiet" not in explain_cadence_block([]).lower()
    assert "cadence" in explain_cadence_block(["quiet hours"]).lower()


def test_explain_escalation_and_confidence() -> None:
    assert "No escalation" in explain_escalation({})
    assert "escalation" in explain_escalation({"editorial_escalate": True}).lower()
    assert "confidence_score" in explain_confidence_summary(
        {"editorial_confidence": {"confidence_score": 0.5}}
    )
