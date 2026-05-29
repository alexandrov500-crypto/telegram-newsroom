from __future__ import annotations

import json
import os

import pytest

from app.editorial.desk_filter import evaluate_desk_filter
from app.editorial.identity import load_editorial_identity
from app.editorial.publish_policy import evaluate_publish_policy
from app.editorial.scoring_engine import score_story
from app.editorial.signal_ranking import rank_story_signal
from app.editorial.source_tiers import aggregate_source_tier, classify_source
from app.observability.newsroom_ops import newsroom_ops_snapshot, record_publish_latency_ms
from publisher.public_renderer import render_public_post_html
from publisher.publish_formatting import build_channel_message_html


def test_high_signal_ranking() -> None:
    text = (
        "Росстат: дефляция в России замедлилась в январе, "
        "индекс потребительских цен показал снижение давления."
    )
    escore = score_story(text=text, sources=["@cb_economics", "@tnews365"])
    signal = rank_story_signal(text, escore, sources=["@cb_economics", "@tnews365"])
    assert signal.signal_score >= 0.50
    assert signal.reject_reason is None
    assert signal.attention_potential >= 0.35
    assert signal.repost_probability >= 0.45
    tier = aggregate_source_tier(["@cb_economics", "@tnews365"])
    assert tier.tier <= 2


def test_low_quality_content_rejected() -> None:
    text = "лол мем про крипту 😂🤣 to the moon 100x"
    escore = score_story(text=text, sources=["@random_aggregator_xyz"])
    desk = evaluate_desk_filter(text, escore, sources=["@random_aggregator_xyz"])
    assert not desk.publish


def test_public_render_clean() -> None:
    body = """Quality: 0.9
Duplicates: 2

Apple удалила приложения из App Store.

Почему это важно:
Россия — крупнейший рынок удалений вне Китая.
"""
    html = render_public_post_html(body, json.dumps([{"channel": "@cb_economics"}]))
    assert "Quality" not in html
    assert "Duplicates" not in html
    assert "Почему это важно" in html
    assert "Apple" in html


def test_source_attribution_footer() -> None:
    src = json.dumps([{"channel": "@cb_economics", "message_id": 1}])
    html = build_channel_message_html("Заголовок\n\nТекст.", src, draft_id=1)
    assert "Источник:" in html
    assert "@cb_economics" in html
    assert "(1)" not in html


def test_tabloid_content_blocked() -> None:
    text = "Шокирующая правда: вы не поверите, какой мем сегодня разлетелся по чатам"
    escore = score_story(text=text, sources=["@random_aggregator_xyz"])
    desk = evaluate_desk_filter(text, escore, sources=["@random_aggregator_xyz"])
    assert not desk.publish


def test_manual_review_flow() -> None:
    text = (
        "ЦБ РФ повысил ключевую ставку на 200 б.п. Парламент обсуждает отставку премьера "
        "на фоне политического кризиса и возможных досрочных выборов."
    )
    escore = score_story(text=text, sources=["@cb_economics", "@tnews365"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics", "@tnews365"])
    assert desk.publish
    policy = evaluate_publish_policy(text, escore, desk, sources=["@cb_economics", "@tnews365"])
    assert policy.manual_review_required
    assert not policy.auto_publish_eligible


def test_publish_latency_threshold() -> None:
    record_publish_latency_ms(120_000.0, breaking=False)
    snap = newsroom_ops_snapshot()
    lat = snap["publish_latency_ms"]
    assert lat["sla_threshold_ms"] >= 60_000
    assert lat["p50"] is not None or lat["p50"] is None


def test_duplicate_suppression_signal() -> None:
    text = "Bitcoin price moved slightly on low volume trading session."
    escore = score_story(text=text, sources=["@decenter"])
    signal = rank_story_signal(text, escore, sources=["@decenter"], category="market")
    assert signal.signal_score < 0.55 or signal.editorial_usefulness < 0.6


def test_tier1_source_authority() -> None:
    tier, auth = classify_source("reuters")
    assert tier == 1
    assert auth >= 0.9


def test_curated_growth_sources_have_tier2_authority() -> None:
    tier, auth = classify_source("@rbc_news")
    assert tier == 2
    assert auth >= 0.7
    tier2, auth2 = classify_source("@banksta")
    assert tier2 == 2
    assert auth2 >= 0.7


def test_editorial_identity_niches() -> None:
    ident = load_editorial_identity()
    assert "macro" in ident.primary_niches
    assert ident.exclude_general_feed
