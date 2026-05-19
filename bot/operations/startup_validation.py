from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from bot.operations.runtime import OperationsPlatform
    from bot.settings import BotSettings
    from bot.staging.observability_validation import TelemetryHealthReport
    from bot.staging.telegram_connectivity import TelegramConnectivityReport

logger = logging.getLogger(__name__)

# Deterministic execution order (stable across runs and nodes).
CHECK_ORDER: tuple[str, ...] = (
    "env.staging_live_flags",
    "env.telegram_token",
    "env.staging_digest_channel",
    "env.operator_chat",
    "env.shadow_publish",
    "db.writable",
    "deps.redis",
    "deps.postgres",
    "feeds.configured",
    "telemetry.metrics",
    "telemetry.tracing",
    "telegram.connectivity",
    "burnin.active",
    "safety.production_blocklist",
)


@dataclass(frozen=True)
class StartupCheck:
    """Single startup check with a stable identifier."""

    check_id: str
    name: str
    passed: bool
    detail: str
    required: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "required": self.required,
        }


@dataclass(frozen=True)
class StartupValidationReport:
    """Aggregated startup validation result."""

    passed: bool
    checks: tuple[StartupCheck, ...]
    fingerprint: str
    staging_mode: bool
    node_role: str

    @property
    def failed_required(self) -> tuple[StartupCheck, ...]:
        return tuple(c for c in self.checks if c.required and not c.passed)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "fingerprint": self.fingerprint,
            "staging_mode": self.staging_mode,
            "node_role": self.node_role,
            "checks": [c.to_dict() for c in self.checks],
        }

    def operator_summary(self) -> str:
        lines = [
            "Startup validation",
            f"  Result: {'PASS' if self.passed else 'FAIL'}",
            f"  Fingerprint: {self.fingerprint}",
            f"  Role: {self.node_role} staging={self.staging_mode}",
            "",
        ]
        for c in self.checks:
            mark = "PASS" if c.passed else "FAIL"
            req = "required" if c.required else "optional"
            lines.append(f"  [{mark}] {c.check_id} ({req}): {c.detail}")
        if self.failed_required:
            lines.append("")
            lines.append(f"  Blocking: {', '.join(c.check_id for c in self.failed_required)}")
        return "\n".join(lines)


def _fingerprint(checks: tuple[StartupCheck, ...]) -> str:
    payload = json.dumps([c.to_dict() for c in checks], sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


class StartupValidationRunner:
    """Unified, deterministic startup validation for staging and production."""

    @classmethod
    def run(
        cls,
        *,
        settings: BotSettings,
        db_path: Path | None = None,
        rss_feed_count: int = 0,
        telegram_report: TelegramConnectivityReport | None = None,
        telemetry: TelemetryHealthReport | None = None,
        operations_platform: OperationsPlatform | None = None,
        node_role: str = "operator",
    ) -> StartupValidationReport:
        staging = settings.is_staging
        collectors: dict[str, StartupCheck] = {}

        collectors["env.staging_live_flags"] = cls._check_staging_live_flags(settings, staging)
        collectors["env.telegram_token"] = cls._check_env_token(settings)
        collectors["env.staging_digest_channel"] = cls._check_digest_channel(settings, staging)
        collectors["env.operator_chat"] = cls._check_operator_chat(settings, staging)
        collectors["env.shadow_publish"] = cls._check_shadow_mode(settings, staging)
        collectors["db.writable"] = cls._check_db(db_path)
        collectors["deps.redis"] = cls._check_redis()
        collectors["deps.postgres"] = cls._check_postgres()
        collectors["feeds.configured"] = cls._check_feeds(rss_feed_count, staging)
        collectors["telemetry.metrics"] = cls._check_metrics(settings, telemetry)
        collectors["telemetry.tracing"] = cls._check_tracing(telemetry)
        collectors["telegram.connectivity"] = cls._check_telegram(telegram_report, staging)
        collectors["burnin.active"] = cls._check_burnin(operations_platform, staging, node_role)
        collectors["safety.production_blocklist"] = cls._check_blocklist(settings, staging)

        checks = tuple(collectors[cid] for cid in CHECK_ORDER if cid in collectors)
        failed_required = any(c.required and not c.passed for c in checks)
        report = StartupValidationReport(
            passed=not failed_required,
            checks=checks,
            fingerprint=_fingerprint(checks),
            staging_mode=staging,
            node_role=node_role,
        )
        cls._record_metrics(report)
        cls._log_report(report)
        return report

    @classmethod
    def run_smoke(cls) -> StartupValidationReport:
        """Lightweight smoke checks without live Telegram (CLI / self-check)."""
        from bot.config import load_settings

        settings = load_settings()
        telemetry = None
        try:
            from bot.staging.observability_validation import validate_startup_telemetry

            telemetry = validate_startup_telemetry(metrics_enabled=settings.metrics_enabled)
        except Exception:
            pass
        db_path = None
        try:
            from bot.storage.db import default_db_path, init_database

            db_path = init_database(default_db_path())
        except Exception:
            pass
        return cls.run(
            settings=settings,
            db_path=db_path,
            rss_feed_count=len(settings.rss_feed_list),
            telemetry=telemetry,
            node_role=os.getenv("NODE_ROLE", "operator"),
        )

    @staticmethod
    def _record_metrics(report: StartupValidationReport) -> None:
        try:
            from bot.observability.metrics import record_startup_validation

            record_startup_validation(report.passed, report.checks)
        except Exception:
            pass

    @staticmethod
    def _log_report(report: StartupValidationReport) -> None:
        logger.info(
            "event=startup_validation passed=%s fingerprint=%s failed_required=%d",
            report.passed,
            report.fingerprint,
            len(report.failed_required),
        )
        for check in report.checks:
            logger.info(
                "event=startup_check check_id=%s passed=%s required=%s detail=%s",
                check.check_id,
                check.passed,
                check.required,
                check.detail[:200],
            )

    @staticmethod
    def _check_env_token(settings: BotSettings) -> StartupCheck:
        ok = bool(settings.telegram_bot_token.strip())
        return StartupCheck(
            "env.telegram_token",
            "Telegram bot token",
            ok,
            "configured" if ok else "TELEGRAM_BOT_TOKEN missing",
            required=True,
        )

    @staticmethod
    def _check_digest_channel(settings: BotSettings, staging: bool) -> StartupCheck:
        ok = settings.staging_publish_channel_id is not None
        if not staging:
            return StartupCheck(
                "env.staging_digest_channel",
                "Publish channel",
                ok,
                "configured" if ok else "optional in dev",
                required=False,
            )
        return StartupCheck(
            "env.staging_digest_channel",
            "Staging digest channel",
            ok,
            "configured" if ok else "TELEGRAM_DIGEST_CHANNEL_ID or TELEGRAM_CHANNEL_ID required",
            required=True,
        )

    @staticmethod
    def _check_operator_chat(settings: BotSettings, staging: bool) -> StartupCheck:
        ok = settings.telegram_operator_chat_id is not None
        return StartupCheck(
            "env.operator_chat",
            "Operator chat",
            ok,
            "configured" if ok else "TELEGRAM_OPERATOR_CHAT_ID unset",
            required=staging,
        )

    @staticmethod
    def _check_shadow_mode(settings: BotSettings, staging: bool) -> StartupCheck:
        if not staging:
            return StartupCheck(
                "env.shadow_publish",
                "Shadow publish mode",
                True,
                "not staging",
                required=False,
            )
        from bot.runtime.state import runtime_state

        shadow = runtime_state.shadow_publish_only or settings.shadow_publish_only
        auto_off = not runtime_state.auto_approval_enabled
        ok = shadow and auto_off
        return StartupCheck(
            "env.shadow_publish",
            "Shadow publish safety",
            ok,
            f"shadow_publish_only={shadow} auto_approval_enabled={settings.auto_approval_enabled}",
            required=True,
        )

    @staticmethod
    def _check_db(db_path: Path | None) -> StartupCheck:
        if db_path is None:
            return StartupCheck("db.writable", "Database", False, "db_path unavailable", required=True)
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("SELECT 1")
            return StartupCheck("db.writable", "Database", True, str(db_path), required=True)
        except Exception as exc:
            return StartupCheck("db.writable", "Database", False, str(exc)[:200], required=True)

    @staticmethod
    def _redis_required(staging: bool) -> bool:
        if os.getenv("REDIS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"):
            return True
        url = os.getenv("REDIS_URL", "").strip()
        return staging and url.startswith("redis://")

    @staticmethod
    def _check_staging_live_flags(settings: BotSettings, staging: bool) -> StartupCheck:
        if not staging:
            return StartupCheck(
                "env.staging_live_flags",
                "Live Telegram flags",
                True,
                "not staging",
                required=False,
            )
        flags = {
            "TELEGRAM_LIVE_INGEST_ENABLED": settings.telegram_live_ingest_enabled,
            "TELEGRAM_LIVE_COGNITIVE_ENABLED": settings.telegram_live_cognitive_enabled,
            "TELEGRAM_LIVE_BURNIN_HOURLY": settings.telegram_live_burnin_hourly,
            "TELEGRAM_LIVE_APPROVAL_CARDS": settings.telegram_live_approval_cards,
        }
        off = [k for k, v in flags.items() if not v]
        ok = len(off) == 0
        return StartupCheck(
            "env.staging_live_flags",
            "Live Telegram flags",
            ok,
            "all enabled" if ok else f"disabled: {', '.join(off)}",
            required=True,
        )

    @staticmethod
    def _check_redis() -> StartupCheck:
        url = os.getenv("REDIS_URL", "").strip()
        staging = os.getenv("STAGING_MODE", "").strip().lower() in ("1", "true", "yes", "on") or (
            os.getenv("APP_ENV", "").strip().lower() in ("staging", "stage")
        )
        required = StartupValidationRunner._redis_required(staging)
        if not url:
            return StartupCheck(
                "deps.redis",
                "Redis",
                not required,
                "not configured (local ok)" if not required else "REDIS_URL missing",
                required=required,
            )
        try:
            import redis

            client = redis.from_url(url, socket_connect_timeout=3)
            client.ping()
            return StartupCheck("deps.redis", "Redis", True, "ping ok", required=required)
        except Exception as exc:
            return StartupCheck("deps.redis", "Redis", False, str(exc)[:200], required=required)

    @staticmethod
    def _check_postgres() -> StartupCheck:
        url = os.getenv("DATABASE_URL", "").strip()
        staging = os.getenv("STAGING_MODE", "").strip().lower() in ("1", "true", "yes", "on") or (
            os.getenv("APP_ENV", "").strip().lower() in ("staging", "stage")
        )
        if not url or url.startswith("sqlite"):
            return StartupCheck(
                "deps.postgres",
                "Postgres",
                not staging,
                "sqlite or unset",
                required=False,
            )
        if "postgresql" not in url:
            return StartupCheck(
                "deps.postgres",
                "Postgres",
                True,
                "non-postgres DATABASE_URL",
                required=False,
            )
        sync_url = url.replace("postgresql+asyncpg://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://",
        )
        try:
            import psycopg

            with psycopg.connect(sync_url, connect_timeout=4) as conn:
                conn.execute("SELECT 1")
            return StartupCheck("deps.postgres", "Postgres", True, "ping ok", required=staging)
        except Exception as exc:
            return StartupCheck(
                "deps.postgres",
                "Postgres",
                False,
                str(exc)[:200],
                required=staging,
            )

    @staticmethod
    def _check_feeds(count: int, staging: bool) -> StartupCheck:
        ok = count > 0
        return StartupCheck(
            "feeds.configured",
            "RSS feeds",
            ok,
            f"{count} feed URLs" if ok else "no feeds configured",
            required=staging,
        )

    @staticmethod
    def _check_metrics(
        settings: BotSettings,
        telemetry: TelemetryHealthReport | None,
    ) -> StartupCheck:
        if not settings.metrics_enabled:
            return StartupCheck(
                "telemetry.metrics",
                "Prometheus metrics",
                True,
                "metrics disabled",
                required=False,
            )
        missing = telemetry.missing if telemetry else ()
        ok = len(missing) == 0
        return StartupCheck(
            "telemetry.metrics",
            "Prometheus metrics",
            ok,
            "core metrics registered" if ok else f"missing: {', '.join(missing)}",
            required=False,
        )

    @staticmethod
    def _check_tracing(telemetry: TelemetryHealthReport | None) -> StartupCheck:
        if telemetry is None:
            return StartupCheck("telemetry.tracing", "Tracing", True, "not evaluated", required=False)
        detail = f"tracing={'on' if telemetry.tracing_enabled else 'off'} otlp={'yes' if telemetry.otlp_configured else 'no'}"
        return StartupCheck("telemetry.tracing", "Tracing", True, detail, required=False)

    @staticmethod
    def _check_telegram(
        report: TelegramConnectivityReport | None,
        staging: bool,
    ) -> StartupCheck:
        if report is None:
            return StartupCheck(
                "telegram.connectivity",
                "Telegram API",
                not staging,
                "not evaluated (run bot startup for live check)",
                required=staging,
            )
        return StartupCheck(
            "telegram.connectivity",
            "Telegram API",
            report.passed,
            report.bot_username or "connectivity failed",
            required=staging,
        )

    @staticmethod
    def _check_burnin(
        ops: OperationsPlatform | None,
        staging: bool,
        node_role: str,
    ) -> StartupCheck:
        from bot.distributed.config import role_allows_operator

        if not staging or not role_allows_operator(node_role):
            return StartupCheck("burnin.active", "Burn-in", True, "not required", required=False)
        if ops is None:
            return StartupCheck("burnin.active", "Burn-in", False, "ops platform unavailable", required=False)
        active = ops.repository.active_burnin()
        ok = active is not None
        detail = f"run_id={active['run_id']} profile={active.get('profile')}" if active else "no active run"
        return StartupCheck("burnin.active", "Burn-in", ok, detail, required=False)

    @staticmethod
    def _check_blocklist(settings: BotSettings, staging: bool) -> StartupCheck:
        if not staging:
            return StartupCheck(
                "safety.production_blocklist",
                "Production blocklist",
                True,
                "not staging",
                required=False,
            )
        blocked = settings.production_channel_blocklist_set
        publish = settings.staging_publish_channel_id
        overlap = publish in blocked if publish and blocked else False
        ok = not overlap
        return StartupCheck(
            "safety.production_blocklist",
            "Production blocklist",
            ok,
            f"blocked_ids={len(blocked)} overlap_with_publish={overlap}",
            required=True,
        )

    @classmethod
    def _check_health_endpoint(cls) -> StartupCheck:
        url = os.getenv("STAGING_HEALTH_URL", "http://127.0.0.1:8080/health")
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                ok = r.status == 200
                return StartupCheck(
                    "health.endpoint",
                    "Health HTTP",
                    ok,
                    url,
                    required=False,
                )
        except Exception as exc:
            return StartupCheck(
                "health.endpoint",
                "Health HTTP",
                False,
                str(exc)[:200],
                required=False,
            )
