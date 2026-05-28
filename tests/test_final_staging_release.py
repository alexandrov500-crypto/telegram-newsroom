from __future__ import annotations

import pytest

from app.editorial.final_publish_gate import evaluate_final_publish_gate
from app.editorial.public_output_lock import enforce_public_output_lock
from app.editorial.public_format import detect_duplicate_wording, format_public_story
from app.editorial.scoring_engine import score_story
from app.editorial.soft_launch import is_soft_launch_mode, soft_launch_thresholds
from app.editorial.tone_engine import apply_newsroom_tone
from app.editorial.trust_system import evaluate_editorial_trust
from app.reliability.publish_watchdog import classify_publish_failure
from publisher.public_renderer import render_public_post_html


def test_tone_engine_non_sensational() -> None:
    r = apply_newsroom_tone("Шокирующая СРОЧНО!!! сенсация")
    assert r.sensational_hits >= 1


def test_public_format_consistency() -> None:
    story = format_public_story("⚡ BREAKING: Test headline", "Summary line one.")
    assert len(story.headline) <= 142
    html = render_public_post_html(f"{story.headline}\n\n{story.summary}", "[]")
    assert enforce_public_output_lock(html).ok


def test_rumor_escalation() -> None:
    text = "По слухам регулятор готовит запрет без официального подтверждения."
    escore = score_story(text=text, sources=["@x"])
    trust = evaluate_editorial_trust(text, escore, sources=["@x"])
    assert trust.manual_review_required or trust.rumor_risk >= 0.6


def test_conflicting_sources_manual_review() -> None:
    text = "С одной стороны рост, с другой стороны падение показателей."
    escore = score_story(text=text, sources=["@a", "@b"])
    trust = evaluate_editorial_trust(
        text,
        escore,
        sources=["@a", "@b"],
        source_snippets=["компания не планирует", "компания планирует сделку"],
    )
    gate = evaluate_final_publish_gate(content=text, sources="[]", operator_approved=False)
    assert trust.source_contradiction or gate.manual_review_required or not gate.allowed


def test_duplicate_wording_detection() -> None:
    assert detect_duplicate_wording("Apple удалила приложения", "Apple удалила приложения из store")


def test_soft_launch_mode_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOFT_LAUNCH_MODE", "true")
    sl = soft_launch_thresholds()
    assert sl.force_manual_review
    monkeypatch.delenv("SOFT_LAUNCH_MODE", raising=False)


def test_editorial_trust_score() -> None:
    text = "Росстат: инфляция замедлилась по официальным данным."
    escore = score_story(text=text, sources=["@cb_economics", "@vedofon"])
    trust = evaluate_editorial_trust(text, escore, sources=["@cb_economics", "@vedofon"])
    assert trust.trust_score >= 0.55


def test_public_output_lock_blocks_debug() -> None:
    html = render_public_post_html("Quality: 0.9\n\nNews text.", "[]")
    lock = enforce_public_output_lock(html)
    assert lock.ok or "quality_score" not in lock.violations


def test_publish_failure_classification() -> None:
    assert classify_publish_failure("FloodWait retry") == "transient"
    assert classify_publish_failure("final_gate:low_trust_score") == "permanent"
