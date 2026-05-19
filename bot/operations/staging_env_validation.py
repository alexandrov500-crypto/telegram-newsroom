from __future__ import annotations

import os
import re
from dataclasses import dataclass

from bot.settings import BotSettings

_CHANNEL_ID = re.compile(r"^-100\d+$")
_BOT_TOKEN = re.compile(r"^\d+:[A-Za-z0-9_-]{20,}$")


@dataclass(frozen=True)
class EnvFieldIssue:
    name: str
    detail: str
    remediation: str


@dataclass(frozen=True)
class StagingEnvReport:
    passed: bool
    issues: tuple[EnvFieldIssue, ...]

    def failed_names(self) -> tuple[str, ...]:
        return tuple(i.name for i in self.issues)

    def operator_summary(self) -> str:
        if self.passed:
            return "Staging environment: OK"
        lines = ["Staging environment: FAIL", ""]
        for issue in self.issues:
            lines.append(f"  • {issue.name}: {issue.detail}")
            lines.append(f"    → {issue.remediation}")
        return "\n".join(lines)


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _require_bool(name: str, expected: bool, remediation: str) -> EnvFieldIssue | None:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return EnvFieldIssue(name, "unset", remediation)
    actual = raw in ("1", "true", "yes", "on")
    if actual != expected:
        return EnvFieldIssue(
            name,
            f"expected {str(expected).lower()}, got {raw!r}",
            remediation,
        )
    return None


def validate_staging_environment(settings: BotSettings) -> StagingEnvReport:
    """Validate staging/live Telegram env before bot startup (no network)."""
    if not settings.is_staging:
        return StagingEnvReport(passed=True, issues=())

    issues: list[EnvFieldIssue] = []

    token = settings.telegram_bot_token.strip()
    if not token:
        issues.append(
            EnvFieldIssue(
                "TELEGRAM_BOT_TOKEN",
                "missing",
                "Set token from @BotFather in .env",
            )
        )
    elif not _BOT_TOKEN.match(token):
        issues.append(
            EnvFieldIssue(
                "TELEGRAM_BOT_TOKEN",
                "malformed (expected digits:secret)",
                "Copy the full token from @BotFather",
            )
        )

    for var, value in (
        ("TELEGRAM_OPERATOR_CHAT_ID", settings.telegram_operator_chat_id),
        ("TELEGRAM_DIGEST_CHANNEL_ID", settings.telegram_digest_channel_id or settings.telegram_channel_id),
    ):
        if value is None:
            issues.append(
                EnvFieldIssue(var, "unset", f"Add {var}=-100… to .env (supergroup/channel id)")
            )
        elif not _CHANNEL_ID.fullmatch(str(value)):
            issues.append(
                EnvFieldIssue(
                    var,
                    f"invalid format ({value!r})",
                    f"{var} must match -100 followed by digits",
                )
            )

    for check in (
        _require_bool(
            "STAGING_MODE",
            True,
            "Set STAGING_MODE=true for staging deployment",
        ),
        _require_bool(
            "SHADOW_PUBLISH_ONLY",
            True,
            "Keep SHADOW_PUBLISH_ONLY=true until production sign-off",
        ),
        _require_bool(
            "AUTO_APPROVAL_ENABLED",
            False,
            "AUTO_APPROVAL_ENABLED must be false in staging",
        ),
        _require_bool(
            "TELEGRAM_LIVE_INGEST_ENABLED",
            True,
            "Set TELEGRAM_LIVE_INGEST_ENABLED=true for live operator feed",
        ),
        _require_bool(
            "TELEGRAM_LIVE_COGNITIVE_ENABLED",
            True,
            "Set TELEGRAM_LIVE_COGNITIVE_ENABLED=true",
        ),
        _require_bool(
            "TELEGRAM_LIVE_BURNIN_HOURLY",
            True,
            "Set TELEGRAM_LIVE_BURNIN_HOURLY=true",
        ),
        _require_bool(
            "TELEGRAM_LIVE_APPROVAL_CARDS",
            True,
            "Set TELEGRAM_LIVE_APPROVAL_CARDS=true",
        ),
    ):
        if check is not None:
            issues.append(check)

    if settings.staging_strict_startup and not _truthy("STAGING_STRICT_STARTUP"):
        issues.append(
            EnvFieldIssue(
                "STAGING_STRICT_STARTUP",
                "expected true when staging strict mode is required",
                "Set STAGING_STRICT_STARTUP=true",
            )
        )

    if _truthy("OPS_BURNIN_ENABLED") and not os.getenv("OPS_BURNIN_PROFILE", "").strip():
        issues.append(
            EnvFieldIssue(
                "OPS_BURNIN_PROFILE",
                "unset while OPS_BURNIN_ENABLED=true",
                "Set OPS_BURNIN_PROFILE=24h (or 7d)",
            )
        )

    redis_url = os.getenv("REDIS_URL", "").strip()
    if _truthy("REDIS_ENABLED"):
        if not redis_url:
            issues.append(
                EnvFieldIssue(
                    "REDIS_URL",
                    "REDIS_ENABLED=true but REDIS_URL empty",
                    "Set REDIS_URL=redis://redis:6379/0 in Docker staging",
                )
            )
    elif settings.is_staging and redis_url.startswith("redis://"):
        issues.append(
            EnvFieldIssue(
                "REDIS_ENABLED",
                "REDIS_URL set but REDIS_ENABLED not true",
                "Set REDIS_ENABLED=true for clustered staging",
            )
        )

    db_url = os.getenv("DATABASE_URL", "").strip()
    if settings.is_staging and db_url and "postgresql" in db_url:
        if not db_url.startswith("postgresql"):
            issues.append(
                EnvFieldIssue(
                    "DATABASE_URL",
                    "invalid scheme for staging postgres",
                    "Use postgresql+asyncpg://user:pass@postgres:5432/newsroom",
                )
            )

    if not settings.admin_user_id_set:
        issues.append(
            EnvFieldIssue(
                "ADMIN_USER_IDS",
                "no admin user ids configured",
                "Set ADMIN_USER_IDS to your Telegram user id(s) for operator commands",
            )
        )

    return StagingEnvReport(passed=len(issues) == 0, issues=tuple(issues))
