from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from bot.processing.languages import LANG_EN, SUPPORTED_LANGUAGES


@dataclass
class RuntimeState:
    ingestion_paused: bool = False
    dry_run_mode: bool = False
    ai_headlines_enabled: bool = True
    caption_style: str = "optimized"
    headline_mode: str = "medium"
    auto_approval_enabled: bool = False
    enabled_languages: set[str] = field(default_factory=lambda: {LANG_EN})
    primary_publish_language: str | None = None
    startup_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    published_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    telegram_connected: bool = False
    telegram_last_cycle_at: datetime | None = None
    telegram_last_error: str | None = None
    telegram_messages_ingested: int = 0
    last_breaking_signal_at: str | None = None
    signals_detected_session: int = 0
    operational_mode: str = "normal"
    maintenance_mode: bool = False
    staging_mode: bool = False
    shadow_publish_only: bool = False
    autonomous_passive: bool = False
    soft_degraded: bool = False
    ingestion_interval_multiplier: float = 1.0

    def is_language_enabled(self, language: str) -> bool:
        return language in self.enabled_languages

    def toggle_language(self, language: str) -> bool:
        if language not in SUPPORTED_LANGUAGES:
            return False
        if language in self.enabled_languages:
            if len(self.enabled_languages) <= 1:
                return True
            self.enabled_languages.discard(language)
            return False
        self.enabled_languages.add(language)
        return True


runtime_state = RuntimeState()
