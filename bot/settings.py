from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from bot.processing.languages import (
    DEFAULT_ENABLED_LANGUAGES,
    LANG_EN,
    LANG_RU,
    SUPPORTED_LANGUAGES,
    normalize_language_code,
)

_CHANNEL_ID_PATTERN = re.compile(r"^-100\d+$")
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class BotSettings(BaseSettings):
    """Typed configuration loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    runtime_profile: str = Field(default="", alias="RUNTIME_PROFILE")
    staging_mode: bool = Field(default=False, alias="STAGING_MODE")
    shadow_publish_only: bool = Field(default=False, alias="SHADOW_PUBLISH_ONLY")
    staging_strict_startup: bool = Field(default=False, alias="STAGING_STRICT_STARTUP")
    production_strict_startup: bool = Field(
        default=False,
        alias="PRODUCTION_STRICT_STARTUP",
    )
    go_live_strict_startup: bool = Field(default=False, alias="GO_LIVE_STRICT_STARTUP")
    go_live_emergency_contacts: str = Field(
        default="",
        alias="GO_LIVE_EMERGENCY_CONTACTS",
    )
    go_live_startup_ping: bool = Field(default=True, alias="GO_LIVE_STARTUP_PING")
    go_live_executive_dashboard: bool = Field(
        default=True,
        alias="GO_LIVE_EXECUTIVE_DASHBOARD",
    )
    staging_feeds_path: str = Field(
        default="config/feeds.staging.yaml",
        alias="STAGING_FEEDS_PATH",
    )
    ops_burnin_profile: str = Field(default="24h", alias="OPS_BURNIN_PROFILE")

    telegram_live_ingest_enabled: bool = Field(
        default=False,
        alias="TELEGRAM_LIVE_INGEST_ENABLED",
    )
    telegram_live_ingest_chat_id: int | None = Field(
        default=None,
        alias="TELEGRAM_LIVE_INGEST_CHAT_ID",
    )
    telegram_live_ingest_min_priority: float = Field(
        default=0.65,
        alias="TELEGRAM_LIVE_INGEST_MIN_PRIORITY",
    )
    telegram_live_cognitive_enabled: bool = Field(
        default=True,
        alias="TELEGRAM_LIVE_COGNITIVE_ENABLED",
    )
    telegram_live_burnin_hourly: bool = Field(
        default=True,
        alias="TELEGRAM_LIVE_BURNIN_HOURLY",
    )
    telegram_live_incident_enabled: bool = Field(
        default=True,
        alias="TELEGRAM_LIVE_INCIDENT_ENABLED",
    )
    telegram_live_approval_cards: bool = Field(
        default=True,
        alias="TELEGRAM_LIVE_APPROVAL_CARDS",
    )
    telegram_live_contradiction_threshold: int = Field(
        default=12,
        alias="TELEGRAM_LIVE_CONTRADICTION_THRESHOLD",
    )
    telegram_ops_agg_window_sec: int = Field(
        default=120,
        alias="TELEGRAM_OPS_AGG_WINDOW_SEC",
    )
    telegram_ops_digest_interval_sec: int = Field(
        default=1800,
        alias="TELEGRAM_OPS_DIGEST_INTERVAL_SEC",
    )
    telegram_ops_max_messages_per_hour: int = Field(
        default=45,
        alias="TELEGRAM_OPS_MAX_MSG_PER_HOUR",
    )
    telegram_ops_fatigue_threshold: float = Field(
        default=0.72,
        alias="TELEGRAM_OPS_FATIGUE_THRESHOLD",
    )
    telegram_ops_quiet_hour_start: int | None = Field(
        default=None,
        alias="TELEGRAM_OPS_QUIET_HOUR_START",
    )
    telegram_ops_quiet_hour_end: int | None = Field(
        default=None,
        alias="TELEGRAM_OPS_QUIET_HOUR_END",
    )

    telegram_bot_token: str = Field(alias="TELEGRAM_BOT_TOKEN")
    telegram_channel_id: int | None = Field(default=None, alias="TELEGRAM_CHANNEL_ID")
    telegram_digest_channel_id: int | None = Field(
        default=None,
        alias="TELEGRAM_DIGEST_CHANNEL_ID",
    )
    telegram_operator_chat_id: int | None = Field(
        default=None,
        alias="TELEGRAM_OPERATOR_CHAT_ID",
    )
    production_channel_blocklist: str = Field(
        default="",
        alias="PRODUCTION_CHANNEL_BLOCKLIST",
    )
    telegram_channel_en: int | None = Field(default=None, alias="TELEGRAM_CHANNEL_EN")
    telegram_channel_ru: int | None = Field(default=None, alias="TELEGRAM_CHANNEL_RU")
    target_channel_id: int | None = Field(default=None, alias="TARGET_CHANNEL_ID")

    rss_feeds: str = Field(default="", alias="RSS_FEEDS")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")

    semantic_similarity_threshold: float = Field(
        default=0.72,
        alias="SEMANTIC_SIMILARITY_THRESHOLD",
    )
    high_trust_sources: str = Field(
        default="reuters,bloomberg,ap",
        alias="HIGH_TRUST_SOURCES",
    )

    telegram_api_id: int | None = Field(default=None, alias="TELEGRAM_API_ID")
    telegram_api_hash: str | None = Field(default=None, alias="TELEGRAM_API_HASH")
    telegram_session_name: str = Field(
        default="newsroom_session",
        alias="TELEGRAM_SESSION_NAME",
    )
    telegram_source_channels: str = Field(
        default="",
        alias="TELEGRAM_SOURCE_CHANNELS",
    )
    source_channels: str = Field(default="", alias="SOURCE_CHANNELS")

    admin_user_ids: str = Field(default="", alias="ADMIN_USER_IDS")
    admin_user_id: str = Field(default="", alias="ADMIN_USER_ID")

    auto_approval_enabled: bool = Field(default=False, alias="AUTO_APPROVAL_ENABLED")
    newsroom_languages: str = Field(default="ru,en", alias="NEWSROOM_LANGUAGES")

    health_http_port: int = Field(default=8080, alias="HEALTH_HTTP_PORT")
    health_http_bind: str = Field(default="0.0.0.0", alias="HEALTH_HTTP_BIND")
    metrics_enabled: bool = Field(default=True, alias="METRICS_ENABLED")
    structured_logging: bool = Field(default=True, alias="STRUCTURED_LOGGING")
    log_json_file: str | None = Field(default=None, alias="LOG_JSON_FILE")

    alert_chat_id: int | None = Field(default=None, alias="ALERT_CHAT_ID")
    alert_cooldown_sec: int = Field(default=300, alias="ALERT_COOLDOWN_SEC")

    watchdog_enabled: bool = Field(default=True, alias="WATCHDOG_ENABLED")
    watchdog_interval_sec: int = Field(default=30, alias="WATCHDOG_INTERVAL_SEC")
    queue_backlog_alert_threshold: int = Field(
        default=200,
        alias="QUEUE_BACKLOG_ALERT_THRESHOLD",
    )

    openai_cost_per_1k_input_usd: float = Field(
        default=0.00015,
        alias="OPENAI_COST_PER_1K_INPUT_USD",
    )
    openai_cost_per_1k_output_usd: float = Field(
        default=0.0006,
        alias="OPENAI_COST_PER_1K_OUTPUT_USD",
    )

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def _coalesce_bot_token(cls, value: Any) -> Any:
        if value:
            return value
        import os

        return os.getenv("BOT_TOKEN", "").strip() or value

    @field_validator(
        "telegram_channel_id",
        "telegram_channel_en",
        "telegram_channel_ru",
        "telegram_digest_channel_id",
        "telegram_operator_chat_id",
        "telegram_live_ingest_chat_id",
        "target_channel_id",
        "telegram_api_id",
        "telegram_ops_quiet_hour_start",
        "telegram_ops_quiet_hour_end",
        "alert_chat_id",
        mode="before",
    )
    @classmethod
    def _empty_optional_none(cls, value: Any) -> Any:
        if value is None or value == "":
            return None
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in ("prod", "production")

    @property
    def strict_startup_required(self) -> bool:
        """Hard-fail startup when Telegram/operator checks fail."""
        if self.staging_strict_startup and self.is_staging:
            return True
        if self.production_strict_startup or self.go_live_strict_startup:
            return True
        return self.is_production and (
            self.production_strict_startup or self.go_live_strict_startup
        )

    @property
    def go_live_emergency_contact_set(self) -> frozenset[int]:
        raw = self.go_live_emergency_contacts.strip()
        if not raw:
            return self.admin_user_id_set
        ids: set[int] = set()
        for part in raw.split(","):
            token = part.strip()
            if token:
                try:
                    ids.add(int(token))
                except ValueError:
                    continue
        return frozenset(ids) if ids else self.admin_user_id_set

    @property
    def is_staging(self) -> bool:
        if self.staging_mode:
            return True
        return self.app_env.strip().lower() in ("staging", "stage")

    @property
    def production_channel_blocklist_set(self) -> frozenset[int]:
        ids: set[int] = set()
        for part in self.production_channel_blocklist.split(","):
            token = part.strip()
            if not token:
                continue
            try:
                ids.add(int(token))
            except ValueError:
                continue
        return frozenset(ids)

    @property
    def staging_publish_channel_id(self) -> int | None:
        """Digest/staging channel used for shadow publishes."""
        for candidate in (self.telegram_digest_channel_id, self.telegram_channel_id):
            validated = self._validated_channel(candidate, "staging")
            if validated is not None:
                return validated
        return None

    @property
    def rss_feed_list(self) -> tuple[str, ...]:
        return tuple(url.strip() for url in self.rss_feeds.split(",") if url.strip())

    @property
    def high_trust_source_set(self) -> frozenset[str]:
        tokens = {
            part.strip().lower()
            for part in self.high_trust_sources.split(",")
            if part.strip()
        }
        return frozenset(tokens) if tokens else frozenset({"reuters", "bloomberg", "ap"})

    @property
    def telegram_source_channel_list(self) -> tuple[str, ...]:
        raw = self.telegram_source_channels.strip() or self.source_channels.strip()
        if not raw:
            return ()
        return tuple(part.strip() for part in raw.split(",") if part.strip())

    @property
    def admin_user_id_set(self) -> frozenset[int]:
        raw = self.admin_user_ids.strip() or self.admin_user_id.strip()
        if not raw:
            return frozenset()
        ids: set[int] = set()
        for part in raw.split(","):
            token = part.strip()
            if not token:
                continue
            try:
                ids.add(int(token))
            except ValueError:
                continue
        return frozenset(ids)

    @property
    def enabled_languages(self) -> frozenset[str]:
        langs: set[str] = set()
        for part in self.newsroom_languages.split(","):
            code = normalize_language_code(part.strip())
            if code:
                langs.add(code)
        return frozenset(langs) if langs else DEFAULT_ENABLED_LANGUAGES

    def _validated_channel(self, raw: int | str | None, name: str) -> int | None:
        if raw is None:
            return None
        token = str(raw).strip()
        if not token:
            return None
        if not _CHANNEL_ID_PATTERN.fullmatch(token):
            return None
        return int(token)

    @property
    def primary_channel_id(self) -> int | None:
        for candidate in (
            self.telegram_channel_id,
            self.target_channel_id,
            self.telegram_channel_en,
        ):
            validated = self._validated_channel(candidate, "primary")
            if validated is not None:
                return validated
        return self._validated_channel(self.telegram_channel_id, "primary")

    @property
    def primary_channels(self) -> dict[str, int]:
        """Language → Telegram channel id (RU + EN only)."""
        channels: dict[str, int] = {}
        en_id = self._validated_channel(
            self.telegram_channel_en or self.primary_channel_id,
            "en",
        )
        ru_id = self._validated_channel(self.telegram_channel_ru, "ru")
        if en_id is not None:
            channels[LANG_EN] = en_id
        if ru_id is not None:
            channels[LANG_RU] = ru_id
        return channels

    @property
    def telegram_channels(self) -> dict[str, int]:
        return dict(self.primary_channels)

    def telethon_configured(self) -> bool:
        return (
            self.telegram_api_id is not None
            and bool(self.telegram_api_hash)
            and bool(self.telegram_source_channel_list)
        )

    @property
    def rss_feeds_tuple(self) -> tuple[str, ...]:
        return self.rss_feed_list


def load_settings() -> BotSettings:
    return BotSettings()
