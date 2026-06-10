"""Tests for Productized Editorial OS (PEOS)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.product_os.channel_substitution_engine import evaluate_channel_substitution
from app.editorial.product_os.content_format import ContentFormat, classify_content_format
from app.editorial.product_os.contextual_cta import CTAType, select_contextual_cta
from app.editorial.product_os.peos_controller import enrich_draft_with_product_os
from app.editorial.product_os.product_gravity import PGAction, compute_product_gravity
from app.editorial.product_os.replacement_loop import ReplacementStage, classify_replacement_stage
from app.editorial.product_os.state import product_os_snapshot, record_peos_evaluation
from app.editorial.product_os.virality_v2 import compute_reference_forward_score


@pytest.fixture(autouse=True)
def _enable_peos(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_PRODUCT_OS", "true")


def test_cse_valid_multi_domain() -> None:
    text = (
        "Fed raised rates. Markets reacted. OpenAI announced model. "
        "Почему важно: decision for investors. Ментальная модель."
    )
    cse = evaluate_channel_substitution(text, cluster_size=2, cross_topic_breadth=3)
    assert cse.valid is True
    assert cse.channels_replaced_estimate >= 3


def test_reference_forward_score_triggers() -> None:
    text = (
        "Срочно: Fed cut rates.\n\n"
        "Что произошло: markets moved.\n\n"
        "Почему важно: cross-domain signal for investors.\n\n"
        "Единая картина из нескольких источников."
    )
    ref = compute_reference_forward_score(text, cluster_size=3, cross_domain_density=0.6, has_why_it_matters=True)
    assert ref.total >= 55
    assert ref.trigger_forward is True


def test_product_gravity_flagship() -> None:
    pg = compute_product_gravity(
        quality_score=75,
        cross_domain_density=0.8,
        substitution_score=80,
        clarity=85,
        reference_forward_total=78,
        novelty_hint=0.7,
    )
    assert pg.total >= 70
    assert pg.action in {PGAction.FLAGSHIP, PGAction.PUBLISH}


def test_contextual_cta_no_spam_on_breaking() -> None:
    cta = select_contextual_cta(content_format=ContentFormat.SIGNAL, is_breaking=True)
    assert cta.cta_type == CTAType.NONE
    assert cta.line == ""


def test_contextual_cta_digest_replacement() -> None:
    cta = select_contextual_cta(content_format=ContentFormat.DIGEST)
    assert cta.cta_type == CTAType.DIGEST
    assert "10 каналов" in cta.line


def test_replacement_loop_dependency() -> None:
    loop = classify_replacement_stage(pg_total=75, reference_forward_score=72, substitution_score=80)
    assert loop.stage == ReplacementStage.DEPENDENCY


def test_classify_content_format_digest() -> None:
    assert classify_content_format("Утренняя сводка: итоги дня", force_digest=True) == ContentFormat.DIGEST


def test_enrich_draft_with_product_os(tmp_path: Path) -> None:
    body = (
        "Fed повысила ставку.\n\n"
        "Почему важно: инвесторы пересматривают риск.\n\n"
        "Рынки NASDAQ и crypto отреагировали. OpenAI в фокусе.\n\n"
        "Глобальный контекст. Ментальная модель для решений."
    )
    layer = {
        "ueos": {"score": {"total": 80.0}},
        "audience_unification": {"reader_simulation": {"cross_interest_breadth": 4}},
        "flagship_post": False,
    }
    _, extras = enrich_draft_with_product_os(
        body,
        runtime_dir=str(tmp_path),
        editorial_category="macro",
        quality_score=62.0,
        is_breaking=False,
        publishing_mode="core",
        sources=["@vedomosti", "@rbc_news"],
        cluster_size=2,
        layer_extras=layer,
    )
    assert "product_os" in extras
    peos = extras["product_os"]
    assert "product_gravity" in peos
    assert "channel_substitution" in peos
    assert peos.get("content_format") in {"context", "insight", "model", "signal", "digest"}
    assert "contextual_cta" in peos


def test_product_os_state(tmp_path: Path) -> None:
    record_peos_evaluation(
        str(tmp_path),
        pg_total=78.0,
        substitution_score=72.0,
        forward_prediction=68.0,
        cta_type="insight",
        content_format="insight",
        published=True,
    )
    snap = product_os_snapshot(str(tmp_path))
    assert snap["evaluated_today"] == 1
    assert snap["published_today"] == 1
    assert snap["pg_avg"] > 0


def test_peos_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_PRODUCT_OS", "false")
    out, extras = enrich_draft_with_product_os(
        "test",
        runtime_dir=None,
        editorial_category="news",
        quality_score=50,
        is_breaking=False,
        publishing_mode="core",
        sources=[],
    )
    assert out == "test"
    assert extras == {}
