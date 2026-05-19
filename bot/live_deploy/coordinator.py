from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from bot.live_deploy.executive_report import ExecutiveGoLiveReport
from bot.live_deploy.first_72h import First72HMode
from bot.live_deploy.publication_guard import LivePublicationGuard
from bot.live_deploy.repository import LiveDeployRepository
from bot.live_deploy.settings import LiveDeploySettings

logger = logging.getLogger(__name__)


@dataclass
class LiveDeployCoordinator:
    settings: LiveDeploySettings
    repository: LiveDeployRepository
    first_72h: First72HMode
    publication_guard: LivePublicationGuard
    executive: ExecutiveGoLiveReport
    _signals_fn: Callable[[], dict[str, Any]] | None = None
    _tick: int = 0
    _hours_elapsed: float = 0.0

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self, *, production_start_at: str | None = None) -> None:
        from bot.ops_playbook.settings import OpsPlaybookSettings

        start_at = production_start_at or OpsPlaybookSettings.default_production_start()
        self.repository.init_state(production_start_at=start_at)
        logger.info("event=live_deploy_installed first_72h=%s", self.first_72h.active())

    async def maybe_send_report(
        self,
        report_key: str,
        *,
        notify: Callable[[str], Any] | None = None,
    ) -> bool:
        if not self.executive.should_send(report_key):
            return False
        sig = self._signals_fn() if self._signals_fn else {}
        text = self.executive.build(report_key, sig)
        if notify is not None:
            await notify(text)
        self.executive.mark_sent(report_key)
        logger.info("event=executive_report_sent key=%s", report_key)
        return True

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        self._tick += 1
        sig = dict(signals or (self._signals_fn() if self._signals_fn else {}))
        self._hours_elapsed = self.first_72h.hours_since_start()
        first_72h_active = self.first_72h.active()

        reports_due: list[str] = []
        if self._tick == 1:
            reports_due.append("startup")
        if 0.9 <= self._hours_elapsed < 1.5:
            reports_due.append("first_hour")
        if 23 <= self._hours_elapsed < 25:
            reports_due.append("24h")
        if 71 <= self._hours_elapsed < 73:
            reports_due.append("72h")

        return {
            "first_72h_active": first_72h_active,
            "hours_elapsed": round(self._hours_elapsed, 2),
            "reports_due": reports_due,
            "thresholds": self.first_72h.thresholds(),
        }

    def notify_publication_blocked(
        self,
        *,
        pending_news_id: int,
        blockers: tuple[str, ...],
    ) -> str:
        return (
            f"⚠️ <b>Publish quarantined</b> #{pending_news_id}\n"
            f"Routed to shadow.\n"
            f"Blockers: {', '.join(blockers[:4])}"
        )

    def prelaunch_checklist(self, checks: dict[str, bool]) -> tuple[bool, list[str]]:
        required = (
            "env_valid",
            "telegram_permissions",
            "redis_healthy",
            "postgres_healthy",
            "openai_configured",
            "rollout_safe",
            "ga_readiness",
            "rc1_lockdown",
            "operator_allowlist",
            "rollback_snapshot",
            "certification",
        )
        failed = [k for k in required if not checks.get(k, False)]
        return len(failed) == 0, failed
