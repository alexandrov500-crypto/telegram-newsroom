from __future__ import annotations

from dataclasses import dataclass

from app.editorial.trust_mode import evaluate_trust_mode, is_high_trust_mode


@dataclass(frozen=True)
class _Settings:
    newsroom_trust_mode: str = "high"


def test_trust_mode_off_allows() -> None:
    v = evaluate_trust_mode("Neutral market update.", settings=_Settings(newsroom_trust_mode="off"))
    assert v.allowed
    assert v.reason == "trust_mode_off"


def test_high_trust_blocks_rumor() -> None:
    text = "По слухам регулятор готовит запрет без официального подтверждения."
    v = evaluate_trust_mode(text, sources=["@unknown_feed"], settings=_Settings())
    assert not v.allowed
    assert v.permanent_block


def test_high_trust_tier3_single_source_manual() -> None:
    text = "Компания X объявила о сделке с партнёром Y в понедельник."
    v = evaluate_trust_mode(text, sources=["@niche_blog"], settings=_Settings())
    assert not v.allowed
    assert v.manual_review_required
    assert not v.permanent_block


def test_is_high_trust_mode() -> None:
    assert is_high_trust_mode(_Settings())
