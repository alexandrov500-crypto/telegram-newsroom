"""Tests for Editorial Growth Dominance Layer."""

from __future__ import annotations

from app.editorial.growth_dominance.arbitration import arbitrate_stability_vs_growth
from app.editorial.growth_dominance.attention_design import evaluate_attention_design
from app.editorial.growth_dominance.dominance_loops import DominanceLoop, classify_dominance_loop
from app.editorial.growth_dominance.gravity import compute_gravity_score
from app.editorial.growth_dominance.hashtag_engine import infer_growth_hashtag
from app.editorial.growth_dominance.source_graph import evaluate_cluster_source_graph


def test_gravity_high_for_breaking_with_layers() -> None:
    text = (
        "Fed повысила ставку на 50 б.п.\n\n"
        "Это важно: инфляция остаётся выше цели.\n\n"
        "Дальше рынки ожидают новых данных по CPI."
    )
    att = evaluate_attention_design(text, post_type="breaking")
    g = compute_gravity_score(
        text,
        quality_score=62.0,
        is_breaking=True,
        post_type="breaking",
        has_hook=att.has_hook,
        has_meaning=att.has_meaning,
        has_implication=att.has_implication,
    )
    assert g.total >= 60
    assert g.action in {"priority_boost", "publish_in_slot"}


def test_gravity_tier_digest_only() -> None:
    text = "Краткая заметка без структуры."
    g = compute_gravity_score(text, quality_score=42.0, post_type="news")
    assert g.action in {"digest_merge", "reject_or_synthesis", "publish_in_slot"}


def test_dominance_loop_awareness() -> None:
    loop = classify_dominance_loop(
        "Срочно: OpenAI представила новую модель",
        is_breaking=True,
        gravity=85,
    )
    assert loop == DominanceLoop.AWARENESS


def test_dominance_loop_retention_for_digest() -> None:
    loop = classify_dominance_loop(
        "Утренняя сводка: 5 вещей до открытия рынка",
        post_type="digest",
    )
    assert loop == DominanceLoop.RETENTION


def test_growth_hashtag_ai() -> None:
    tag = infer_growth_hashtag("OpenAI released GPT-5 with new capabilities")
    assert tag == "#AIImpact"


def test_single_class_source_downgrade() -> None:
    ev = evaluate_cluster_source_graph(["@vedomosti", "@rbc_news"], cluster_size=1)
    assert ev.single_class_only is True
    assert ev.downgrade_to_digest is True


def test_arbitration_stability_on_silence() -> None:
    arb = arbitrate_stability_vs_growth(
        anti_pause_active=True,
        silence_risk=True,
        gravity_action="reject_or_synthesis",
        gravity_total=35,
        growth_reject=True,
        attention_passes=False,
        source_downgrade_digest=False,
        publishing_mode="elastic_fill",
    )
    assert arb.stability_override is True
    assert arb.publish is True


def test_arbitration_high_gravity_boost() -> None:
    arb = arbitrate_stability_vs_growth(
        anti_pause_active=False,
        silence_risk=False,
        gravity_action="priority_boost",
        gravity_total=85,
        growth_reject=False,
        attention_passes=True,
        source_downgrade_digest=False,
    )
    assert arb.priority_boost is True
    assert arb.winner.value == "growth"


def test_attention_design_rejects_just_reporting() -> None:
    att = evaluate_attention_design("По данным Reuters, компания объявила о сделке.")
    assert att.just_reporting is True or not att.has_meaning
