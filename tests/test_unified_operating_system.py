"""Tests for Unified Editorial Operating System (UEOS)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.unified_operating_system.arbitration import arbitrate_layer_conflicts
from app.editorial.unified_operating_system.audience_replacement import evaluate_channel_replacement
from app.editorial.unified_operating_system.content_principle import evaluate_content_principle, enrich_content_principle
from app.editorial.unified_operating_system.cross_source_intelligence_merger import merge_world_signal
from app.editorial.unified_operating_system.daily_autopilot import AutopilotMode, resolve_autopilot_mode
from app.editorial.unified_operating_system.hashtag_strategy_v2 import apply_hashtag_strategy_v2, infer_primary_hashtag
from app.editorial.unified_operating_system.state import record_ueos_decision, ueos_state_snapshot
from app.editorial.unified_operating_system.ueos_controller import enrich_draft_with_ueos
from app.editorial.unified_operating_system.ueos_score import UEOSAction, compute_ueos_score
from app.editorial.unified_operating_system.user_reality_model import evaluate_user_reality


@pytest.fixture(autouse=True)
def _enable_ueos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_UNIFIED_OPERATING_SYSTEM", "true")
    monkeypatch.setenv("EDITORIAL_AUDIENCE_UNIFICATION_LAYER", "false")
    monkeypatch.setenv("EDITORIAL_GROWTH_DOMINANCE_LAYER", "false")


def test_urm_multi_topic_reader() -> None:
    text = "Fed raised rates. Bitcoin fell. OpenAI launched GPT-5. Sanctions expanded."
    urm = evaluate_user_reality(text)
    assert len(urm.matched_topics) >= 3
    assert urm.reader_unification_score >= 50


def test_csim_merges_cluster() -> None:
    texts = [
        "Oil prices jump on OPEC cut",
        "Oil prices jump on OPEC cut — Reuters confirms",
        "Energy stocks rally in Europe",
    ]
    result = merge_world_signal(texts, topic_hint="energy")
    assert result.merged_events >= 1
    assert result.same_event_detected is True
    assert "Что произошло" in result.body


def test_ueos_score_flagship() -> None:
    score = compute_ueos_score(
        ues_total=90,
        crs_total=88,
        gravity_total=92,
        reader_unification=85,
        cross_source_intelligence=82,
        attention_design={"has_hook": True, "has_meaning": True, "has_implication": True, "passes": True},
    )
    assert score.total >= 88
    assert score.action == UEOSAction.PUBLISH_FLAGSHIP
    assert score.skip_cadence_cap is True


def test_ueos_score_reject_in_core() -> None:
    score = compute_ueos_score(
        ues_total=40,
        crs_total=35,
        gravity_total=30,
        reader_unification=40,
        cross_source_intelligence=30,
        publishing_mode="core",
    )
    assert score.action == UEOSAction.REJECT


def test_layer_arbitration_anti_pause_wins() -> None:
    arb = arbitrate_layer_conflicts(
        anti_pause_active=True,
        publishing_mode="elastic_fill",
        gravity_total=45,
        crs_total=55,
        ues_total=50,
        dominance_reject=True,
        auh_reject=True,
        cluster_size=1,
        quality_score=48,
        replaces_channels=False,
    )
    assert arb.stability_override is True
    assert "anti_pause_vs_rejection" in arb.conflicts_resolved


def test_layer_arbitration_auh_wins_over_gravity() -> None:
    arb = arbitrate_layer_conflicts(
        anti_pause_active=False,
        publishing_mode="core",
        gravity_total=55,
        crs_total=72,
        ues_total=68,
        dominance_reject=False,
        auh_reject=False,
        cluster_size=2,
        quality_score=58,
        replaces_channels=True,
    )
    assert arb.auh_wins_over_gravity is True


def test_channel_replacement_requires_three_channels() -> None:
    weak = evaluate_channel_replacement("Local city event only", cross_topic_breadth=0, cluster_size=1)
    assert weak.replaces_external_channels is False

    strong = evaluate_channel_replacement(
        "Fed raised rates affecting global markets and AI sector investment decisions. "
        "Почему важно: системный сигнал для инвесторов. Глобальный контекст.",
        cross_topic_breadth=4,
        cluster_size=2,
        crs_total=75,
    )
    assert strong.replaces_external_channels is True
    assert strong.estimated_channels_replaced >= 3


def test_content_principle_detects_missing_layers() -> None:
    check = evaluate_content_principle("Fed cut rates.")
    assert check.complete is False
    assert check.needs_rewrite is True


def test_content_principle_enrich() -> None:
    out, meta = enrich_content_principle("Company X announced merger.")
    assert meta["rewritten"] is True
    assert len(out) > 30


def test_hashtag_v2_single_primary() -> None:
    tag = infer_primary_hashtag("OpenAI released new GPT model with disruption")
    assert tag == "#AIDisruption"
    out, meta = apply_hashtag_strategy_v2("OpenAI released new GPT model", editorial_category="ai")
    assert meta["primary"] == "#AIDisruption"
    assert out.count("#") <= 3


def test_autopilot_signal_mode() -> None:
    mode = resolve_autopilot_mode(
        is_breaking=True,
        gravity_total=85,
        anti_pause_active=False,
        publishing_mode="core",
        cluster_size=1,
        quality_score=70,
        compression_required=False,
    )
    assert mode.mode == AutopilotMode.SIGNAL
    assert mode.immediate_publish is True


def test_autopilot_compression_mode() -> None:
    mode = resolve_autopilot_mode(
        is_breaking=False,
        gravity_total=55,
        anti_pause_active=False,
        publishing_mode="core",
        cluster_size=3,
        quality_score=48,
        compression_required=True,
    )
    assert mode.mode == AutopilotMode.COMPRESSION
    assert mode.use_csim is True


def test_enrich_draft_with_ueos_full_flow(tmp_path: Path) -> None:
    body = (
        "Fed повысила ставку на 50 b.p.\n\n"
        "Почему важно: инфляция выше цели.\n\n"
        "Рынки NASDAQ отреагировали. OpenAI в фокусе. Bitcoin volatile.\n\n"
        "Глобальный контекст: ментальная модель для инвесторов."
    )
    layer = {
        "editorial_dominance": {
            "gravity": {"total": 78.0},
            "attention_design": {"has_hook": True, "has_meaning": True, "has_implication": True, "passes": True},
        },
        "audience_unification": {
            "crs": {"total": 72.0},
            "ues": {"total": 75.0},
            "reader_simulation": {"reader_unification_score": 70.0, "cross_interest_breadth": 4},
        },
    }
    packaged, extras = enrich_draft_with_ueos(
        body,
        runtime_dir=str(tmp_path),
        editorial_category="macro",
        quality_score=62.0,
        is_breaking=False,
        publishing_mode="core",
        cluster_size=2,
        cluster_texts=[body, "Markets react to Fed move"],
        layer_extras=layer,
    )
    assert "ueos" in extras
    assert extras["ueos"]["decision"] in {
        "publish",
        "publish_flagship",
        "publish_digest",
        "compress_and_publish",
        "stability_fallback",
    }
    assert extras["ueos"]["hashtag_v2"]["applied"] is True
    assert "#" in packaged


def test_ueos_state_tracking(tmp_path: Path) -> None:
    record_ueos_decision(
        str(tmp_path),
        ueos_total=82.0,
        action="publish",
        conflicts=["auh_vs_egdl"],
        compression=True,
        replacement_score=4,
        published=True,
    )
    snap = ueos_state_snapshot(str(tmp_path))
    assert snap["evaluated_today"] == 1
    assert snap["published_today"] == 1
    assert snap["compression_events_today"] == 1


def test_ueos_disabled_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_UNIFIED_OPERATING_SYSTEM", "false")
    out, extras = enrich_draft_with_ueos(
        "test",
        runtime_dir=None,
        editorial_category="news",
        quality_score=50,
        is_breaking=False,
        publishing_mode="core",
    )
    assert out == "test"
    assert extras == {}
