"""Editorial intelligence layer: fingerprints, evolution, relevance, trends, entities, feedback."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from db.models import RawPost
from editorial.cluster_rank import evaluate_cluster_for_pipeline
from editorial.entities import extract_entities, normalize_entity
from editorial.event_models import EventEvolution
from editorial.events import classify_event_evolution, compute_event_fingerprint
from editorial.feedback import feedback_boost_from_stats
from editorial.intelligence_store import reset_intelligence_files_for_tests
from editorial.relevance import compute_unified_relevance
from editorial.topic_memory import bump_topic, export_topic_snapshot
from editorial.trends import detect_topic_trends


def _post(pid: int, *, text: str = "Bitcoin and Ethereum traded in USA markets.", ch: str = "wire_a") -> RawPost:
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    return RawPost(
        id=pid,
        channel_name=ch,
        message_id=pid,
        text=text,
        created_at=now,
        collected_at=now,
    )


def test_event_fingerprint_stable_under_reorder() -> None:
    a = _post(1, ch="a")
    b = _post(2, ch="b")
    c = _post(3, ch="c")
    fp1 = compute_event_fingerprint([a, b, c])
    fp2 = compute_event_fingerprint([c, a, b])
    assert fp1 == fp2


def test_classify_event_evolution_exact_fingerprint() -> None:
    cur = "abc123"
    hist = [{"fingerprint": cur, "combined_text_excerpt": "older excerpt"}]
    ev = classify_event_evolution(cur, combined_text="totally different words here", history=hist)
    assert ev.kind == "update"
    assert ev.continuity_score == 1.0


def test_duplicate_similarity_lowers_relevance_total() -> None:
    posts = [_post(10), _post(11, ch="wire_b")]
    evo = EventEvolution("new", 0.1, None, ())
    rel_none = compute_unified_relevance(
        posts,
        channel_scores={},
        evolution=evo,
        topic_row={"count": 2, "last_ts": 1.0, "fingerprints": []},
        entity_hits=3,
        duplicate_similarity_pct=None,
        feedback_boost=0.0,
    )
    rel_dup = compute_unified_relevance(
        posts,
        channel_scores={},
        evolution=evo,
        topic_row={"count": 2, "last_ts": 1.0, "fingerprints": []},
        entity_hits=3,
        duplicate_similarity_pct=96.0,
        feedback_boost=0.0,
    )
    assert rel_dup.total < rel_none.total
    assert "duplicate_high" in rel_dup.notes


def test_detect_topic_trends_empty_runtime(tmp_path) -> None:
    rd = str(tmp_path)
    reset_intelligence_files_for_tests(rd)
    out = detect_topic_trends(rd)
    assert out.get("bursts") == []


def test_feedback_boost_monotone_with_acceptance() -> None:
    hi = {"counts": {"published": 80, "rejected": 10, "pending": 2}}
    lo = {"counts": {"published": 5, "rejected": 40, "pending": 1}}
    assert feedback_boost_from_stats(hi) >= feedback_boost_from_stats(lo)


def test_normalize_entity_collapses_whitespace() -> None:
    assert normalize_entity("  Foo\tBAR\n") == "foo bar"


def test_extract_entities_dedupes_normalized(tmp_path) -> None:
    reset_intelligence_files_for_tests(str(tmp_path))
    text = "Bitcoin and bitcoin meet USA and USA"
    ents = extract_entities(text)
    norms = [e.normalized for e in ents]
    assert len(set(norms)) == len(norms)


def test_bump_topic_then_export_snapshot(tmp_path) -> None:
    rd = str(tmp_path)
    reset_intelligence_files_for_tests(rd)
    bump_topic(rd, topic_hint="ai regulation", fingerprint="fp1")
    bump_topic(rd, topic_hint="ai regulation", fingerprint="fp2")
    rows = export_topic_snapshot(rd, limit=10)
    assert rows and int(rows[0].get("count") or 0) >= 2


def test_evaluate_cluster_for_pipeline_shape(tmp_path) -> None:
    rd = str(tmp_path)
    reset_intelligence_files_for_tests(rd)
    posts = [_post(101), _post(102, ch="wire_b")]
    settings = SimpleNamespace(runtime_state_dir=rd)
    evo = EventEvolution("new", 0.05, None, ())
    dec = evaluate_cluster_for_pipeline(
        posts,
        settings=settings,
        evolution=evo,
        topic_hint="markets",
        fingerprint="fpz",
        combined_text="hello world",
        channel_scores={},
        feedback_stats=None,
        duplicate_similarity_pct=None,
        entity_hits=2,
    )
    assert dec.relevance.total >= 0.0
    assert dec.relevance.total <= 100.0
    assert isinstance(dec.suppress, bool)
