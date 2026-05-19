from __future__ import annotations

from pathlib import Path

from bot.rc1.activation.workflow import PublicActivationOrchestrator
from bot.rc1.baselines.engine import BaselineEngine
from bot.rc1.config.registry import NewsroomConfigRegistry
from bot.rc1.config.validation import ConfigValidationGraph
from bot.rc1.coordinator import Rc1Coordinator
from bot.rc1.dashboard.launch import LaunchDashboardBuilder
from bot.rc1.hardening.failure_modes import FailureModeGuard
from bot.rc1.lockdown import Rc1LockdownController
from bot.rc1.operator.ux import OperatorUxHub
from bot.rc1.profiling.runtime import RuntimeProfiler
from bot.rc1.repository import Rc1Repository
from bot.rc1.settings import RC1_BUILD_ID, Rc1Settings
from bot.rc1.validation.live_traffic import LiveTrafficValidator


def build_rc1_stack(
    db_path: Path,
    *,
    quiet_hour_start: int | None = None,
    quiet_hour_end: int | None = None,
) -> Rc1Coordinator:
    settings = Rc1Settings.from_env()
    repo = Rc1Repository(db_path)
    lockdown = Rc1LockdownController(build_id=RC1_BUILD_ID)
    if settings.lockdown_mode:
        lockdown.active = True
    return Rc1Coordinator(
        settings=settings,
        repository=repo,
        config_registry=NewsroomConfigRegistry.collect(build_id=RC1_BUILD_ID),
        config_validator=ConfigValidationGraph(),
        lockdown=lockdown,
        profiler=RuntimeProfiler(),
        baselines=BaselineEngine(repo),
        failure_guard=FailureModeGuard(),
        activation=PublicActivationOrchestrator(repo),
        live_validation=LiveTrafficValidator(),
        operator_ux=OperatorUxHub(
            quiet_hour_start=quiet_hour_start,
            quiet_hour_end=quiet_hour_end,
        ),
        dashboard=LaunchDashboardBuilder(),
    )
