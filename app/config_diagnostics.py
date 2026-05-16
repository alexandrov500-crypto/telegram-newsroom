"""Non-secret diagnostics for ``config-doctor`` CLI and startup summaries."""

from __future__ import annotations

import os
from typing import Any

from app.config import Settings
from app.versioning import public_metadata

# Vars required by ``load_settings()`` before a Settings object exists.
_REQUIRED_FOR_LOAD_SETTINGS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "BOT_TOKEN",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "ADMIN_USER_ID",
    "TARGET_CHANNEL_ID",
    "SOURCE_CHANNELS",
)

# At least one Telethon credential (validated in load_settings, not single env name).
_TELETHON_ANY_OF: tuple[str, ...] = ("TELETHON_SESSION_PATH", "TELETHON_SESSION_STRING")


def missing_env_for_bootstrap() -> list[str]:
    """Names missing or empty in ``os.environ`` (read-only)."""
    missing: list[str] = []
    for name in _REQUIRED_FOR_LOAD_SETTINGS:
        if not (os.getenv(name) or "").strip():
            missing.append(name)
    if not any((os.getenv(n) or "").strip() for n in _TELETHON_ANY_OF):
        missing.append("TELETHON_SESSION_PATH|TELETHON_SESSION_STRING")
    return missing


def build_config_doctor_report(settings: Settings) -> dict[str, Any]:
    """Structured report for CLI / logs (no tokens)."""
    meta = public_metadata()
    return {
        "ok": True,
        **meta,
        "deployment_profile": settings.deployment_profile,
        "safe_mode": bool(settings.safe_mode),
        "dry_run": bool(settings.dry_run),
        "redis_enabled": bool(settings.redis_enabled),
        "database_backend": "sqlite" if "sqlite" in settings.database_url.lower() else "other",
        "runtime_state_dir": settings.runtime_state_dir,
        "job_queue_prefix": settings.job_queue_prefix,
        "health_http_port": int(settings.health_http_port),
        "pipeline_interval_minutes": int(settings.pipeline_interval_minutes),
        "openai_model": settings.openai_model,
    }


def startup_config_summary_lines(settings: Settings) -> list[str]:
    """Short human lines for bootstrap / installer output."""
    r = build_config_doctor_report(settings)
    lines = [
        f"app_version={r.get('app_version')} profile={r.get('deployment_profile')}",
        f"safe_mode={r.get('safe_mode')} dry_run={r.get('dry_run')} redis={r.get('redis_enabled')}",
        f"runtime_state_dir={r.get('runtime_state_dir')}",
        f"queue_prefix={r.get('job_queue_prefix')}",
    ]
    return lines
