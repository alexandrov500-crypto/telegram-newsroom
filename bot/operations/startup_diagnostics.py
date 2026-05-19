from __future__ import annotations

import json
import logging
import os
from typing import Any

from bot.operations.staging_env_validation import StagingEnvReport
from bot.operations.startup_validation import StartupValidationReport
from bot.settings import BotSettings
from bot.staging.telegram_connectivity import TelegramConnectivityReport

logger = logging.getLogger(__name__)


def format_startup_ok_summary(**components: str) -> str:
    lines = ["[STARTUP OK]"]
    for key, status in components.items():
        lines.append(f"{key}={status}")
    return "\n".join(lines)


def log_startup_ok(**components: str) -> None:
    summary = format_startup_ok_summary(**components)
    logger.info("%s", summary)
    for line in summary.splitlines():
        print(line)


def _redis_diagnostic() -> dict[str, Any]:
    from bot.distributed.redis_client import redis_enabled

    url = os.getenv("REDIS_URL", "").strip()
    if not redis_enabled() and not url:
        return {"enabled": False, "detail": "not configured"}
    try:
        import redis

        client = redis.from_url(url or "redis://localhost:6379/0", socket_connect_timeout=3)
        client.ping()
        return {"enabled": True, "url": url[:80], "ping": "ok"}
    except Exception as exc:
        return {"enabled": redis_enabled(), "url": url[:80], "ping": "fail", "error": str(exc)[:200]}


def _postgres_diagnostic() -> dict[str, Any]:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url or "postgresql" not in url:
        return {"configured": False, "detail": url[:40] or "unset"}
    sync_url = url.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://",
    )
    try:
        import psycopg

        with psycopg.connect(sync_url, connect_timeout=4) as conn:
            conn.execute("SELECT 1")
        return {"configured": True, "ping": "ok"}
    except Exception as exc:
        return {"configured": True, "ping": "fail", "error": str(exc)[:200]}


def _telegram_permission_hints(report: TelegramConnectivityReport | None) -> list[str]:
    if report is None:
        return ["Telegram connectivity was not evaluated"]
    hints: list[str] = []
    if not report.bot_ok:
        hints.append("getMe failed — verify TELEGRAM_BOT_TOKEN")
    for check in report.checks:
        if check.passed:
            continue
        if check.name == "digest":
            hints.append(
                "Digest channel: add bot as admin with Post Messages permission"
            )
        elif check.name == "operator":
            hints.append(
                "Operator chat: add bot to group/supergroup or start bot in private chat"
            )
        else:
            hints.append(f"{check.name}: {check.detail}")
    return hints


def emit_startup_failure_diagnostics(
    *,
    subsystem: str,
    settings: BotSettings,
    env_report: StagingEnvReport | None = None,
    conn_report: TelegramConnectivityReport | None = None,
    startup_report: StartupValidationReport | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Structured operator-facing failure report (logged + printed)."""
    payload: dict[str, Any] = {
        "subsystem": subsystem,
        "staging_mode": settings.is_staging,
        "strict_startup": settings.staging_strict_startup,
        "failed_env_vars": list(env_report.failed_names()) if env_report else [],
        "redis": _redis_diagnostic(),
        "postgres": _postgres_diagnostic(),
        "telegram_hints": _telegram_permission_hints(conn_report),
    }
    if env_report and not env_report.passed:
        payload["env_issues"] = [
            {"name": i.name, "detail": i.detail, "remediation": i.remediation}
            for i in env_report.issues
        ]
    if startup_report and startup_report.failed_required:
        payload["failed_checks"] = [
            {"id": c.check_id, "detail": c.detail} for c in startup_report.failed_required
        ]
    if conn_report:
        payload["telegram_connectivity"] = {
            "bot_ok": conn_report.bot_ok,
            "bot_username": conn_report.bot_username,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "can_post": c.can_post,
                    "detail": c.detail,
                }
                for c in conn_report.checks
            ],
            "errors": conn_report.errors,
        }
    if extra:
        payload["extra"] = extra

    text_lines = [
        "═" * 40,
        f"STARTUP FAILED — {subsystem}",
        "═" * 40,
        "",
    ]
    if env_report and not env_report.passed:
        text_lines.append(env_report.operator_summary())
        text_lines.append("")
    if startup_report and startup_report.failed_required:
        text_lines.append("Blocking startup checks:")
        for c in startup_report.failed_required:
            text_lines.append(f"  • {c.check_id}: {c.detail}")
        text_lines.append("")
    for hint in payload["telegram_hints"]:
        text_lines.append(f"Telegram: {hint}")
    redis_d = payload["redis"]
    if redis_d.get("ping") == "fail":
        text_lines.append(f"Redis: {redis_d.get('error', 'unreachable')}")
    pg_d = payload["postgres"]
    if pg_d.get("ping") == "fail":
        text_lines.append(f"Postgres: {pg_d.get('error', 'unreachable')}")

    text = "\n".join(text_lines)
    logger.critical(
        "event=startup_failure_diagnostics subsystem=%s payload=%s",
        subsystem,
        json.dumps(payload, default=str)[:4000],
    )
    print(text, file=__import__("sys").stderr)
    return text
