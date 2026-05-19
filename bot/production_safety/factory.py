from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.production_safety.coordinator import ProductionSafetyCoordinator
from bot.production_safety.containment import RuntimeContainment
from bot.production_safety.editorial_trust import EditorialTrustEngine
from bot.production_safety.financial_safety import FinancialSafetyController
from bot.production_safety.forensics import ForensicsStore
from bot.production_safety.operator_failover import OperatorFailoverManager
from bot.production_safety.repository import ProductionSafetyRepository
from bot.production_safety.rollout import RolloutController
from bot.production_safety.security import ProductionSecurityLayer
from bot.production_safety.settings import ProductionSafetySettings
from bot.production_safety.telegram_delivery import TelegramDeliveryGuard
from bot.production_safety.circuit_breakers import CircuitBreakerRegistry


def build_production_safety(
    db_path: Path,
    *,
    admin_ids: frozenset[int],
    backup_chat_id: int | None = None,
    dlq_depth_fn: Any = None,
) -> ProductionSafetyCoordinator:
    settings = ProductionSafetySettings.from_env()
    repo = ProductionSafetyRepository(db_path)
    containment = RuntimeContainment(settings)
    if dlq_depth_fn is not None:
        containment.configure_dlq_fn(dlq_depth_fn)
    return ProductionSafetyCoordinator(
        settings=settings,
        repository=repo,
        telegram=TelegramDeliveryGuard(settings),
        financial=FinancialSafetyController(settings),
        editorial_trust=EditorialTrustEngine(settings),
        containment=containment,
        rollout=RolloutController(settings, repo),
        breakers=CircuitBreakerRegistry(),
        forensics=ForensicsStore(repo),
        security=ProductionSecurityLayer(repo),
        operators=OperatorFailoverManager(
            settings,
            repo,
            admin_ids=admin_ids,
            backup_chat_id=backup_chat_id,
        ),
    )
