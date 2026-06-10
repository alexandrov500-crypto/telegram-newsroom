from __future__ import annotations

import pytest

from app.editorial.scoring_engine import EditorialScore
from app.editorial.signal_ranking import rank_story_signal
from app.growth_layer.virality.engine import ViralityScoreEngine
from app.growth_layer.virality.tiers import ViralityTier, classify_virality_tier


def _escore(**kwargs: float) -> EditorialScore:
    base = {
        "relevance_score": 0.7,
        "impact_score": 0.75,
        "urgency_score": 0.2,
        "credibility_score": 0.8,
        "final_priority_score": 55.0,
        "lane": "normal",
        "is_breaking": False,
        "breaking_score": 0.0,
        "reason": "test",
    }
    base.update(kwargs)
    return EditorialScore(**base)


def test_classify_virality_tier_bands() -> None:
    assert classify_virality_tier(25) is ViralityTier.STANDARD
    assert classify_virality_tier(55) is ViralityTier.ENHANCED
    assert classify_virality_tier(82) is ViralityTier.VIRAL_CANDIDATE


def test_virality_engine_uses_signal_ranking_not_duplicate() -> None:
    text = (
        "ЦБ повысил ключевую ставку на 100 б.п. до 21%. "
        "Инфляция замедляется, но остаётся выше цели. "
        "Рынок облигаций переоценивает траекторию."
    )
    escore = _escore(impact_score=0.85)
    signal = rank_story_signal(text, escore, sources=["@cb_economics"], category="macro")
    result = ViralityScoreEngine().score(text=text, signal=signal, escore=escore)
    assert 0 <= result.score <= 100
    assert result.tier is ViralityTier.ENHANCED or result.tier is ViralityTier.VIRAL_CANDIDATE
    assert result.dimensions["novelty"] >= 0.0
    assert result.dimensions["economic_impact"] >= 0.2
    patch = result.to_growth_extras_patch(format_profile="hybrid")
    assert patch["growth"]["virality_score"] == result.score


def test_low_signal_story_stays_standard() -> None:
    text = "Компания обновила корпоративный сайт без финансовых показателей."
    escore = _escore(impact_score=0.05, relevance_score=0.2)
    signal = rank_story_signal(text, escore, sources=["@random"], category="general")
    result = ViralityScoreEngine().score(text=text, signal=signal, escore=escore)
    assert result.score <= 45
    assert result.tier in {ViralityTier.STANDARD, ViralityTier.ENHANCED}


def test_upsert_draft_growth_score_roundtrip() -> None:
    import asyncio

    async def _run() -> None:
        from db.growth_scores_repository import get_draft_growth_score, upsert_draft_growth_score
        from db.models import Draft, DraftStatus
        from db.repository import utcnow
        from db.session import init_db, session_scope

        await init_db("sqlite+aiosqlite:///:memory:")
        async with session_scope() as session:
            draft = Draft(
                content="test",
                content_hash="abc",
                sources="[]",
                status=DraftStatus.PENDING.value,
                created_at=utcnow(),
            )
            session.add(draft)
            await session.flush()
            text = "Fed сохранила ставку. S&P 500 вырос на 1,2%."
            escore = _escore()
            signal = rank_story_signal(text, escore, sources=["@cb_economics"], category="macro")
            result = ViralityScoreEngine().score(text=text, signal=signal, escore=escore)
            await upsert_draft_growth_score(
                session,
                draft_id=int(draft.id),
                result=result,
                format_profile="cb_brief",
            )
            row = await get_draft_growth_score(session, int(draft.id))
            assert row is not None
            assert row.virality_score == result.score
            assert row.virality_tier == result.tier.value

    asyncio.run(_run())
