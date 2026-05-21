"""Editorial governance: ledger, ranking, policies, explainability."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from db.models import RawPost
from editorial.governance.ledger import append_decision, query_decisions, reset_ledger_for_tests
from editorial.governance.operator_controls import (
    boost_source,
    is_emergency_freeze,
    mute_source,
    set_emergency_freeze,
)
from editorial.governance.policies_engine import evaluate_policies, load_governance_rules
from editorial.governance.ranking import rank_clusters, score_cluster_candidate
from editorial.intelligence_store import save_json
from editorial.governance.paths import governance_rules_path


def _post(pid: int, ch: str, text: str, *, hours_ago: float = 0.5) -> RawPost:
    ts = datetime.now(timezone.utc).timestamp() - hours_ago * 3600
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return RawPost(
        id=pid,
        channel_name=ch,
        text=text,
        created_at=dt,
        collected_at=dt,
        message_id=pid,
    )


def test_decision_ledger_append_and_query(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    reset_ledger_for_tests(rd)
    append_decision(
        runtime_dir=rd,
        decision_type="cluster_selected",
        outcome="proceed",
        subject_id="fp-test",
        reason_codes=["high_freshness"],
    )
    rows = query_decisions(rd, limit=5)
    assert len(rows) == 1
    assert rows[0]["decision_type"] == "cluster_selected"
    assert rows[0]["runtime_id"]


def test_deterministic_ranking_stable_tiebreak(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    posts = [
        _post(1, "channel_a", "Breaking energy markets shift in Europe today"),
        _post(2, "channel_b", "Energy markets shift in Europe with new data"),
    ]
    a = score_cluster_candidate(
        posts,
        runtime_dir=rd,
        fingerprint="fp-a",
        topic_hint="energy europe",
        evolution_kind="new",
    )
    b = score_cluster_candidate(
        posts,
        runtime_dir=rd,
        fingerprint="fp-a",
        topic_hint="energy europe",
        evolution_kind="new",
    )
    assert a.weighted_total == b.weighted_total
    assert a.tie_break == b.tie_break
    assert "freshness" in a.stages


def test_rank_clusters_snapshot(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    posts = [_post(3, "reuters", "Central bank raises rates amid inflation")]
    ranked = rank_clusters(
        [{"posts": posts, "fingerprint": "fp-r", "topic_hint": "rates", "evolution_kind": "new"}],
        runtime_dir=rd,
    )
    assert ranked[0]["rank"] == 1
    assert "trace" in ranked[0]


def test_policy_low_trust_blocks(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    rules = load_governance_rules(rd)
    save_json(governance_rules_path(rd), rules)
    from utils.source_reputation import record_reject_for_channels

    record_reject_for_channels(["badsource"] * 20, runtime_dir=rd)
    posts = [_post(10, "badsource", "War and sanctions escalate in region")]
    matches, suppress, reason = evaluate_policies(
        posts,
        runtime_dir=rd,
        topic_key="war",
        dominant_channel="badsource",
    )
    assert suppress or reason or matches


def test_operator_freeze_blocks_ranking(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    set_emergency_freeze(rd, enabled=True, reason="test")
    assert is_emergency_freeze(rd)
    tr = score_cluster_candidate(
        [_post(5, "x", "Sample text for governance freeze test")],
        runtime_dir=rd,
        fingerprint="fp-f",
        topic_hint="test",
    )
    assert tr.hard_block is True
    set_emergency_freeze(rd, enabled=False)


def test_operator_mute_and_boost(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    mute_source(rd, "spam_channel", ttl_sec=120.0, reason="test")
    boost_source(rd, "good_channel", boost=0.1, reason="test")
    tr = score_cluster_candidate(
        [_post(6, "spam_channel", "Muted channel should block")],
        runtime_dir=rd,
        fingerprint="fp-m",
        topic_hint="spam",
    )
    assert tr.hard_block
