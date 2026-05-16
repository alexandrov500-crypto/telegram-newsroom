"""Editorial policy, cadence, suppression TTL, drift, pipeline decision (unit)."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from db.models import RawPost
from editorial.adaptation import adaptive_threshold_overrides
from editorial.cadence import cadence_should_defer_cluster, evaluate_publish_gate, record_publish, topic_dedupe_key
from editorial.diversity import compute_diversity_signals
from editorial.event_models import EventEvolution
from editorial.intelligence_store import editorial_policies_path, reset_intelligence_files_for_tests, save_json
from editorial.policy import load_editorial_policy_bundle
from editorial.policy_models import ChannelEditorialPolicy, merge_policies
from editorial.relevance import apply_editorial_policy_to_relevance, compute_unified_relevance
from editorial.suppression_memory import bump_duplicate_burst, is_suppression_active, record_suppression_ttl
from editorial.drift_detection import evaluate_editorial_drift
from tests.conftest import minimal_test_settings


def _post(i: int, ch: str = "wire_a") -> RawPost:
    now = datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc)
    return RawPost(
        id=i,
        channel_name=ch,
        message_id=i,
        text="Bitcoin and OpenAI discussed in USA markets.",
        created_at=now,
        collected_at=now,
    )


def test_topic_dedupe_key_stable() -> None:
    assert topic_dedupe_key("  Foo BAR ") == topic_dedupe_key("foo bar")


def test_merge_policy_override() -> None:
    base = ChannelEditorialPolicy()
    merged = merge_policies(base, {"relevance_suppress_below": 25.0, "preferred_substrings": ["bitcoin"]})
    assert merged.relevance_suppress_below == 25.0
    assert "bitcoin" in merged.preferred_substrings


def test_quiet_hours_block_publish() -> None:
    s = minimal_test_settings()
    pol = merge_policies(ChannelEditorialPolicy(), {"quiet_hours_local": [[0, 23]]})
    block, rs = evaluate_publish_gate(s, s.runtime_state_dir, pol, topic_key="x", is_breaking=False)
    assert block is True
    assert rs


def test_breaking_bypasses_quiet_hours() -> None:
    s = minimal_test_settings()
    pol = merge_policies(ChannelEditorialPolicy(), {"quiet_hours_local": [[0, 23]]})
    block, _ = evaluate_publish_gate(s, s.runtime_state_dir, pol, topic_key="x", is_breaking=True)
    assert block is False


def test_suppression_ttl_active(tmp_path) -> None:
    rd = str(tmp_path)
    reset_intelligence_files_for_tests(rd)
    record_suppression_ttl(rd, "fp123", ttl_sec=3600.0, reason="test")
    assert is_suppression_active(rd, "fp123") is True


def test_suppression_ttl_expired(tmp_path) -> None:
    rd = str(tmp_path)
    reset_intelligence_files_for_tests(rd)
    record_suppression_ttl(rd, "fp123", ttl_sec=1.0, reason="test")
    time.sleep(1.15)
    assert is_suppression_active(rd, "fp123") is False


def test_duplicate_burst_counter(tmp_path) -> None:
    rd = str(tmp_path)
    reset_intelligence_files_for_tests(rd)
    assert bump_duplicate_burst(rd) == 1
    assert bump_duplicate_burst(rd) == 2


def test_adaptive_thresholds_low_acceptance() -> None:
    pol = ChannelEditorialPolicy()
    stats = {
        "acceptance_proxy": 0.4,
        "counts": {"published": 3, "rejected": 10, "pending": 1},
        "recent_drafts_sampled": 20,
    }
    out = adaptive_threshold_overrides(stats, pol)
    assert out["relevance_suppress_below"] >= pol.relevance_suppress_below


def test_diversity_low_unique_channels() -> None:
    posts = [_post(1), _post(2, ch="wire_a")]
    d = compute_diversity_signals(posts, "bitcoin", ("bitcoin",))
    assert d.unique_channels == 1


def test_policy_relevance_affinity(tmp_path) -> None:
    posts = [_post(1), _post(2, ch="b")]
    evo = EventEvolution("new", 0.1, None, ())
    rel = compute_unified_relevance(
        posts,
        channel_scores={},
        evolution=evo,
        topic_row={"count": 2, "last_ts": time.time(), "fingerprints": []},
        entity_hits=2,
        duplicate_similarity_pct=None,
        feedback_boost=0.0,
    )
    before = rel.total
    pol = merge_policies(
        ChannelEditorialPolicy(),
        {"preferred_substrings": ["bitcoin"], "topic_affinity_boost_cap": 0.12},
    )
    apply_editorial_policy_to_relevance(
        rel,
        pol,
        topic_hint="bitcoin rally",
        combined_text="bitcoin rally",
        diversity=compute_diversity_signals(posts, "bitcoin rally", ("bitcoin",)),
        topic_row={"count": 2, "last_ts": time.time(), "fingerprints": []},
        evolution=evo,
    )
    assert rel.total >= before


def test_cadence_burst_record_then_defer(tmp_path) -> None:
    rd = str(tmp_path)
    s = replace(minimal_test_settings(), runtime_state_dir=rd)
    reset_intelligence_files_for_tests(rd)
    pol = ChannelEditorialPolicy()
    for _ in range(5):
        record_publish(rd, topic_key="abc")
    defer, reasons = cadence_should_defer_cluster(s, rd, pol, topic_key="abc", urgency=False)
    assert defer is True
    assert reasons


def test_drift_evaluate_append_false(tmp_path) -> None:
    rd = str(tmp_path)
    reset_intelligence_files_for_tests(rd)
    out = evaluate_editorial_drift(
        rd,
        current_metrics={
            "suppression_rate": 0.1,
            "avg_confidence": 0.6,
            "avg_headline_quality": 0.7,
            "manual_edit_rate": 0.1,
        },
        current_feedback={"acceptance_proxy": 0.7},
        append_snapshot=False,
    )
    assert "warnings" in out


def test_load_policy_bundle_json_file(tmp_path) -> None:
    rd = str(tmp_path)
    p = editorial_policies_path(rd)
    p.parent.mkdir(parents=True, exist_ok=True)
    save_json(
        p,
        {
            "version": 1,
            "default": {"relevance_suppress_below": 20.0},
            "channels": {"wire_a": {"relevance_suppress_below": 30.0}},
        },
    )
    s = replace(minimal_test_settings(), runtime_state_dir=rd, editorial_policies_json="{}")
    b = load_editorial_policy_bundle(s)
    assert b.channel_policies["wire_a"].relevance_suppress_below == 30.0


def test_relevance_breakdown_includes_policy_fields() -> None:
    posts = [_post(10), _post(11, ch="x")]
    evo = EventEvolution("new", 0.1, None, ())
    rel = compute_unified_relevance(
        posts,
        channel_scores={},
        evolution=evo,
        topic_row=None,
        entity_hits=1,
        duplicate_similarity_pct=None,
        feedback_boost=0.0,
    )
    d = rel.to_dict()
    assert "policy_delta" in d
    assert "policy_adjustments" in d


def test_unified_pipeline_decision_explainable(tmp_path) -> None:
    from editorial.pipeline_decision import evaluate_unified_cluster_stage
    from editorial.policy import dominant_channel_key, load_editorial_policy_bundle

    rd = str(tmp_path)
    s = replace(minimal_test_settings(), runtime_state_dir=rd)
    reset_intelligence_files_for_tests(rd)
    posts = [_post(1), _post(2, ch="c2")]
    evo = EventEvolution("new", 0.1, None, ())
    bundle = load_editorial_policy_bundle(s)
    uni = evaluate_unified_cluster_stage(
        posts,
        settings=s,
        evolution=evo,
        topic_hint="markets",
        fingerprint="fp_test",
        combined_text="bitcoin market",
        channel_scores={},
        feedback_stats=None,
        duplicate_similarity_pct=None,
        entity_hits=2,
        entity_norms=("bitcoin",),
        policy_bundle=bundle,
        dominant_channel_key=dominant_channel_key(posts),
    )
    d = uni.to_dict()
    assert "score_breakdown" in d and "policy_refs" in d and "adaptation" in d
