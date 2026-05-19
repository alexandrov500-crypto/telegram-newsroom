from __future__ import annotations

from pathlib import Path

import pytest

from bot.production_safety.circuit_breakers import CircuitBreaker
from bot.production_safety.editorial_trust import EditorialTrustEngine, EditorialTrustInput
from bot.production_safety.financial_safety import FinancialSafetyController
from bot.production_safety.repository import ProductionSafetyRepository
from bot.production_safety.rollout import RolloutController
from bot.production_safety.settings import ProductionSafetySettings
from bot.production_safety.telegram_delivery import TelegramDeliveryGuard
from bot.production_safety.types import RolloutStage, StoryTrustState
from bot.storage.db import init_database


@pytest.fixture
def repo(tmp_path: Path) -> ProductionSafetyRepository:
    db = init_database(tmp_path / "prod_safety.db")
    return ProductionSafetyRepository(db)


def test_telegram_floodwait_backoff() -> None:
    guard = TelegramDeliveryGuard(ProductionSafetySettings.from_env())
    delay = guard.record_floodwait(5.0)
    assert delay >= 5.0
    assert guard.stats().floodwait_count_hour >= 1


def test_financial_emergency_mode() -> None:
    fin = FinancialSafetyController(
        ProductionSafetySettings(
            enabled=True,
            daily_budget_usd=10.0,
            emergency_cost_threshold=0.5,
        ),
    )
    fin.record_spend(8.0)
    assert fin.current_mode().value == "EMERGENCY_LOW_COST"


def test_editorial_trust_blocked_on_misinfo() -> None:
    engine = EditorialTrustEngine(ProductionSafetySettings.from_env())
    state = engine.evaluate(
        EditorialTrustInput(
            publish_confidence=0.9,
            source_count=2,
            duplicate_narrative=False,
            misinfo_score=0.9,
            hallucination_suspicion=0.0,
            open_contradictions=0,
            operator_approved=False,
            unsafe_content=False,
        ),
    )
    assert state == StoryTrustState.BLOCKED


def test_rollout_shadow_blocks_publish(repo: ProductionSafetyRepository) -> None:
    settings = ProductionSafetySettings.from_env()
    rollout = RolloutController(settings, repo)
    rollout.set_stage(RolloutStage.INTERNAL_SHADOW)
    ok, reason = rollout.can_publish_now()
    assert not ok
    assert "shadow" in reason


def test_circuit_breaker_opens() -> None:
    br = CircuitBreaker("test", failure_threshold=2, recovery_sec=1.0)
    br.record_failure()
    br.record_failure()
    assert not br.allow_request()


def test_forensics_persist(repo: ProductionSafetyRepository) -> None:
    from bot.production_safety.forensics import ForensicsStore

    store = ForensicsStore(repo)
    tid = store.record(story_id=42, trace_type="decision", payload={"decision": "approve"})
    assert tid.startswith("tr_")
    traces = repo.get_story_traces(42)
    assert len(traces) == 1
