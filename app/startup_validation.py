from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)

_OPENAI_MODEL_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]{0,127}$")


def _append_runtime_environment_checks(settings: Settings, errors: list[str]) -> None:
    """Filesystem, temp dir, URL shape, and timeout ordering (no network)."""
    if settings.openai_request_timeout_sec <= 0 or settings.openai_http_timeout_sec <= 0:
        errors.append("OpenAI request/HTTP timeouts must be positive")
    if settings.openai_request_timeout_sec > settings.openai_http_timeout_sec:
        errors.append("OPENAI_REQUEST_TIMEOUT_SEC must be <= OPENAI_HTTP_TIMEOUT_SEC")
    if settings.healthcheck_timeout_sec <= 0 or settings.telegram_http_timeout_sec <= 0:
        errors.append("HEALTHCHECK_TIMEOUT_SEC and TELEGRAM_HTTP_TIMEOUT_SEC must be positive")
    if settings.healthcheck_timeout_sec > settings.telegram_http_timeout_sec:
        errors.append("HEALTHCHECK_TIMEOUT_SEC should be <= TELEGRAM_HTTP_TIMEOUT_SEC")

    try:
        from sqlalchemy.engine.url import make_url

        u = make_url(settings.database_url)
    except Exception as exc:
        errors.append(f"DATABASE_URL is not a valid SQLAlchemy URL: {exc}")
        return

    if u.get_backend_name() in ("sqlite", "aiosqlite"):
        db = (u.database or "").strip()
        if db and db != ":memory:":
            try:
                p = Path(db).expanduser().resolve()
                parent = p.parent
                if not parent.exists():
                    errors.append(f"SQLite database directory does not exist: {parent}")
                else:
                    probe = parent / ".newsroom_write_probe"
                    try:
                        probe.write_text("ok", encoding="utf-8")
                        probe.unlink(missing_ok=True)
                    except OSError as exc2:
                        errors.append(f"SQLite database directory is not writable ({parent}): {exc2}")
            except OSError as exc3:
                errors.append(f"SQLite path resolution failed: {exc3}")
    elif "postgresql" in u.get_backend_name():
        if u.database is None or str(u.database).strip() == "":
            errors.append("PostgreSQL DATABASE_URL must include a database name")

    try:
        fd, tmpp = tempfile.mkstemp(prefix="newsroom_startup_probe_")
        os.close(fd)
        os.unlink(tmpp)
    except OSError as exc:
        errors.append(f"System temp directory is not usable: {exc}")

    _append_telethon_session_checks(settings, errors)

    if settings.channel_collect_delay_seconds > 120:
        errors.append("CHANNEL_COLLECT_DELAY_SECONDS must be at most 120 for launch validation")


def _append_telethon_session_checks(settings: Settings, errors: list[str]) -> None:
    """
    Telethon credentials (single source of truth — not checked in shell entrypoint).

    - STRING set → file path parent is not required (string wins if both set).
    - PATH only → parent directory must exist (created by entrypoint under /data).
    - Neither → fatal.
    """
    has_string = bool((settings.telethon_session_string or "").strip())
    has_path = bool((settings.telethon_session_path or "").strip())

    if not has_string and not has_path:
        errors.append("At least one of TELETHON_SESSION_STRING or TELETHON_SESSION_PATH is required")
        return

    if has_string:
        return

    try:
        parent = Path(settings.telethon_session_path or "").expanduser().resolve().parent
        if not parent.exists():
            errors.append(f"TELETHON_SESSION_PATH parent directory must exist ({parent})")
    except OSError as exc:
        errors.append(f"TELETHON_SESSION_PATH invalid: {exc}")


def validate_settings_for_launch(settings: Settings) -> None:
    """
    Fail-fast checks after load_settings(). Raises RuntimeError with a readable message.
    """
    errors: list[str] = []

    if not settings.openai_api_key:
        errors.append("OPENAI_API_KEY is empty")

    if not settings.bot_token or ":" not in settings.bot_token:
        errors.append("BOT_TOKEN looks invalid (expected '12345:ABC...')")

    if settings.admin_user_id <= 0:
        errors.append("ADMIN_USER_ID must be a positive Telegram user id")

    if settings.target_channel_id == 0:
        errors.append("TARGET_CHANNEL_ID must be non-zero (supergroups/channels are often negative, e.g. -100…)")

    if not settings.source_channels:
        errors.append("SOURCE_CHANNELS must list at least one channel")

    if settings.pipeline_interval_minutes < 1 or settings.pipeline_interval_minutes > 24 * 60:
        errors.append("PIPELINE_INTERVAL_MINUTES must be between 1 and 1440")

    if settings.collect_messages_per_channel < 1:
        errors.append("COLLECT_MESSAGES_PER_CHANNEL must be at least 1")

    if settings.min_raw_posts_for_ai < 1:
        errors.append("MIN_RAW_POSTS_FOR_AI must be at least 1")

    if not (0.5 <= settings.draft_similarity_threshold <= 1.0):
        errors.append("DRAFT_SIMILARITY_THRESHOLD must be between 0.5 and 1.0")

    if settings.retention_processed_raw_days < 0 or settings.retention_processed_raw_days > 3650:
        errors.append("RETENTION_PROCESSED_RAW_DAYS must be between 0 and 3650")

    if settings.retention_rejected_draft_days < 0 or settings.retention_rejected_draft_days > 3650:
        errors.append("RETENTION_REJECTED_DRAFT_DAYS must be between 0 and 3650")

    if settings.diagnostics_interval_minutes < 0 or settings.diagnostics_interval_minutes > 24 * 60:
        errors.append("DIAGNOSTICS_INTERVAL_MINUTES must be between 0 and 1440")

    if settings.metrics_summary_interval_minutes < 0 or settings.metrics_summary_interval_minutes > 24 * 60:
        errors.append("METRICS_SUMMARY_INTERVAL_MINUTES must be between 0 and 1440")

    if settings.sqlite_analyze_interval_hours < 0 or settings.sqlite_analyze_interval_hours > 24 * 30:
        errors.append("SQLITE_ANALYZE_INTERVAL_HOURS must be between 0 and 720")

    if settings.sqlite_vacuum_interval_hours < 0 or settings.sqlite_vacuum_interval_hours > 24 * 120:
        errors.append("SQLITE_VACUUM_INTERVAL_HOURS must be between 0 and 2880")

    if settings.operational_report_interval_hours < 0 or settings.operational_report_interval_hours > 24 * 14:
        errors.append("OPERATIONAL_REPORT_INTERVAL_HOURS must be between 0 and 336")

    if not _OPENAI_MODEL_RE.match(settings.openai_model):
        errors.append(
            f"OPENAI_MODEL looks invalid ({settings.openai_model!r}); "
            "use a non-empty model id (letters, digits, dots, dashes, underscores)"
        )

    from ai.editorial import ALLOWED_HEADLINE_MODES, ALLOWED_SUMMARY_STYLES

    if settings.summary_style not in ALLOWED_SUMMARY_STYLES:
        errors.append(f"SUMMARY_STYLE invalid ({settings.summary_style!r}); use one of {sorted(ALLOWED_SUMMARY_STYLES)}")
    if settings.headline_mode not in ALLOWED_HEADLINE_MODES:
        errors.append(f"HEADLINE_MODE invalid ({settings.headline_mode!r}); use none, json, or prefix")

    _append_runtime_environment_checks(settings, errors)

    if settings.redis_enabled and not settings.redis_url.strip():
        errors.append("REDIS_ENABLED=true requires a non-empty REDIS_URL")

    if settings.deployment_profile == "production":
        if ":memory:" in settings.database_url.lower():
            errors.append("production profile: DATABASE_URL must not use SQLite :memory:")
        if settings.dry_run and os.getenv("ALLOW_PRODUCTION_DRY_RUN", "").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            errors.append("production profile: DRY_RUN=true requires ALLOW_PRODUCTION_DRY_RUN=1")

    if errors:
        msg = "Startup validation failed:\n- " + "\n- ".join(errors)
        logger.error(msg)
        raise RuntimeError(msg)

    if getattr(settings, "safe_mode", False):
        logger.warning(
            "NEWSROOM_SAFE_MODE is enabled — conservative operational mode "
            "(review DRY_RUN and channel sends; see docs/SELF_HOSTING.md)."
        )

    from ops.resilience.startup_checks import emit_validation_result, run_startup_integrity_checks

    emit_validation_result(run_startup_integrity_checks(settings))

    logger.info("Startup validation passed (env, Telegram ids, OpenAI model, retention, intervals)")
