from __future__ import annotations

import os

import pytest

from app.editorial.desk_filter import evaluate_desk_filter
from app.editorial.public_format import detect_duplicate_wording, format_public_story
from app.editorial.publish_policy import evaluate_publish_policy
from app.editorial.scoring_engine import score_story
from app.editorial.soft_launch import is_soft_launch_mode, soft_launch_thresholds
from app.editorial.tone_engine import apply_newsroom_tone, count_sensational_markers
from app.editorial.trust_system import evaluate_editorial_trust
from publisher.public_renderer import render_public_post_html


def test_tone_engine_non_sensational() -> None:
    raw = "Шокирующая СРОЧНО!!! сенсация — узнай правду"
    result = apply_newsroom_tone(raw)
    assert result.sensational_hits >= 1
    assert count_sensational_markers(result.text) < count_sensational_markers(raw)


def test_public_format_consistency() -> None:
    story = format_public_story(
        "⚡ BREAKING: Apple удалила приложения",
        "Краткое summary.\n\nВторой абзац.",
    )
    assert len(story.headline) <= 142
    assert "BREAKING" not in story.headline.upper() or "Apple" in story.headline
    html = render_public_post_html(
        f"{story.headline}\n\n{story.summary}",
        "[]",
        why_it_matters=story.why_it_matters,
    )
    assert "<b>" in html
    assert "Quality" not in html


def test_rumor_escalation() -> None:
    text = "По слухам регулятор готовит запрет на операции банка без официального подтверждения."
    escore = score_story(text=text, sources=["@decenter"])
    trust = evaluate_editorial_trust(text, escore, sources=["@decenter"])
    assert trust.rumor_risk >= 0.6
    assert trust.manual_review_required


def test_conflicting_sources_manual_review() -> None:
    text = "С одной стороны источники утверждают рост, с другой стороны другие отрицают сделку."
    escore = score_story(text=text, sources=["@a", "@b"])
    trust = evaluate_editorial_trust(
        text,
        escore,
        sources=["@a", "@b"],
        source_snippets=["компания не планирует сделку", "компания планирует крупную сделку"],
    )
    assert trust.source_contradiction
    assert trust.manual_review_required
    desk = evaluate_desk_filter(text, escore, sources=["@a", "@b"])
    policy = evaluate_publish_policy(text, escore, desk, sources=["@a", "@b"])
    assert policy.manual_review_required


def test_duplicate_wording_detection() -> None:
    h = "Apple удалила приложения из App Store"
    s = "Apple удалила приложения из App Store по требованию регулятора."
    assert detect_duplicate_wording(h, s)


def test_soft_launch_mode_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOFT_LAUNCH_MODE", "true")
    sl = soft_launch_thresholds()
    assert sl.force_manual_review
    assert sl.auto_publish_signal_min >= 0.78
    assert sl.min_trust_score >= 0.62
    monkeypatch.delenv("SOFT_LAUNCH_MODE", raising=False)
    assert not is_soft_launch_mode()


def test_editorial_trust_score() -> None:
    text = (
        "Росстат опубликовал данные по инфляции. "
        "Показатель снизился в январе согласно официальному отчёту."
    )
    escore = score_story(text=text, sources=["@cb_economics", "@vedofon"])
    trust = evaluate_editorial_trust(text, escore, sources=["@cb_economics", "@vedofon"])
    assert trust.trust_score >= 0.55
    assert trust.corroboration_score >= 0.75
    assert not trust.manual_review_required
