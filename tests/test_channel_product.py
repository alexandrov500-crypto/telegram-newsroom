"""Tests for Channel as Product layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.channel_product.acquisition_attribution import build_acquisition_attribution
from app.editorial.channel_product.controller import enrich_draft_with_channel_product
from app.editorial.channel_product.cta_optimizer import select_cta_variant
from app.editorial.channel_product.growth_loop import GrowthLoopStage, classify_growth_loop
from app.editorial.channel_product.render_bridge import merged_growth_meta_from_extras
from app.editorial.channel_product.state import channel_product_snapshot, record_channel_product_event
from app.editorial.channel_product.viral_mechanics import evaluate_viral_mechanics


@pytest.fixture(autouse=True)
def _enable_channel_product(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_CHANNEL_PRODUCT_LAYER", "true")
    monkeypatch.setenv("CHANNEL_PRODUCT_SHARE_NUDGE", "true")


def test_classify_awareness_loop_for_flagship() -> None:
    loop = classify_growth_loop(ueos_total=90, flagship=True)
    assert loop.stage == GrowthLoopStage.AWARENESS


def test_classify_reference_forward_for_viral() -> None:
    loop = classify_growth_loop(virality_score=70, forwardability=0.6)
    assert loop.stage == GrowthLoopStage.REFERENCE_FORWARD


def test_viral_mechanics_reference_forward_tier() -> None:
    text = (
        "Fed raised rates 50 b.p.\n\n"
        "Почему важно: decision signal for investors and macro risk.\n\n"
        "Ментальная модель: one story."
    )
    v = evaluate_viral_mechanics(text, ueos_total=80, crs_total=72, flagship=False)
    assert v.reference_forward_score >= 55
    assert v.viral_tier in {"reference_forward", "viral_flagship", "enhanced"}


def test_cta_variant_stable_per_post() -> None:
    text = "Fed cut rates affecting global markets"
    a = select_cta_variant(text)
    b = select_cta_variant(text)
    assert a.variant_id == b.variant_id
    assert "Перешлите" in a.share_nudge or "Сохраните" in a.share_nudge


def test_acquisition_attribution_experiment_id() -> None:
    attr = build_acquisition_attribution(
        draft_body="test post body",
        loop_stage="reference_forward",
        cta_variant_id="macro_v0",
        format_profile="growth_brief",
        channel_username="testchannel",
    )
    assert attr.experiment_id.startswith("cp_")
    assert "t.me/testchannel" in attr.deep_link_hint


def test_enrich_draft_with_channel_product(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "hybrid")
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "off")
    body = (
        "Fed повысила ставку.\n\n"
        "Почему важно: инвесторы пересматривают риск.\n\n"
        "Глобальный контекст + ментальная модель."
    )
    layer = {
        "ueos": {"score": {"total": 82.0}, "decision": "publish"},
        "audience_unification": {"crs": {"total": 74.0}},
        "flagship_post": True,
    }
    _, extras = enrich_draft_with_channel_product(
        body,
        runtime_dir=str(tmp_path),
        editorial_category="macro",
        publishing_mode="core",
        layer_extras=layer,
    )
    assert "channel_product" in extras
    assert "growth" in extras
    cp = extras["channel_product"]
    assert cp["enable_share_nudge"] is True
    assert cp["format_profile"] in {"growth_brief", "cb_brief", "subscriber_wire", "format_ab"}
    assert extras["growth"]["experiment_id"]


def test_merged_growth_meta_from_extras() -> None:
    import json

    payload = json.dumps(
        {
            "growth": {"virality_score": 55, "format_profile": "cb_brief"},
            "channel_product": {
                "format_profile": "growth_brief",
                "viral_tier": "reference_forward",
                "reference_forward_score": 72,
                "share_nudge": "Forward test",
            },
        }
    )
    merged = merged_growth_meta_from_extras(payload)
    assert merged is not None
    assert merged["format_profile"] == "growth_brief"
    assert merged["virality_score"] == 72
    assert merged["channel_product"]["share_nudge"] == "Forward test"


def test_channel_product_state(tmp_path: Path) -> None:
    record_channel_product_event(
        str(tmp_path),
        loop_stage="reference_forward",
        viral_tier="reference_forward",
        cta_variant_id="macro_v0",
        reference_forward_score=68.0,
        published=True,
    )
    snap = channel_product_snapshot(str(tmp_path))
    assert snap["evaluated_today"] == 1
    assert snap["published_today"] == 1
    assert snap["loop_distribution"].get("reference_forward") == 1


def test_channel_product_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_CHANNEL_PRODUCT_LAYER", "false")
    out, extras = enrich_draft_with_channel_product(
        "test",
        runtime_dir=None,
        editorial_category="news",
        publishing_mode="core",
    )
    assert out == "test"
    assert extras == {}
