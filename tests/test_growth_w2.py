"""W2 growth engine unit tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.growth.breaking_collapse import evaluate_breaking_collapse, record_breaking_event
from app.growth.engagement_feedback import _bayesian_rate, load_engagement_feedback
from app.growth.topic_fatigue import evaluate_topic_fatigue, record_topic_publish


def test_bayesian_smoothing_prior() -> None:
    assert _bayesian_rate(0.0, 0.0) == 0.35
    assert _bayesian_rate(5.0, 5.0) > 0.35


def test_topic_fatigue_suppresses_after_repeated_publish() -> None:
    with tempfile.TemporaryDirectory() as td:
        for _ in range(6):
            record_topic_publish(runtime_dir=td, topic_key="macro_rates", content="Fed raises rates impact markets")
        v = evaluate_topic_fatigue(runtime_dir=td, topic_key="macro_rates", content="Fed raises rates again")
        assert v.fatigue_score > 0.5


def test_breaking_collapse_duplicate_event() -> None:
    with tempfile.TemporaryDirectory() as td:
        text = "Fed emergency rate cut shocks markets"
        first = evaluate_breaking_collapse(runtime_dir=td, text=text)
        assert not first.collapse
        record_breaking_event(runtime_dir=td, text=text, event_id=first.event_id)
        second = evaluate_breaking_collapse(runtime_dir=td, text=text)
        assert second.collapse


def test_engagement_feedback_empty_cache() -> None:
    with tempfile.TemporaryDirectory() as td:
        fb = load_engagement_feedback(td)
        assert fb.global_engagement == 0.35
