"""Per-channel collect profiling stats and structured log events."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


@dataclass
class ChannelCollectStats:
    channel: str
    started_at: float = field(default_factory=time.perf_counter)
    messages_scanned: int = 0
    messages_fetched: int = 0
    new_rows_written: int = 0
    deduped_rows: int = 0
    media_downloads: int = 0
    media_skipped_existing: int = 0
    exceptions_count: int = 0

    def record_scan(self) -> None:
        self.messages_scanned += 1

    def record_fetched(self) -> None:
        self.messages_fetched += 1

    def record_new(self) -> None:
        self.new_rows_written += 1

    def record_dedup(self) -> None:
        self.deduped_rows += 1

    def record_exception(self) -> None:
        self.exceptions_count += 1

    @property
    def runtime_sec(self) -> float:
        return max(0.0, time.perf_counter() - self.started_at)

    def emit_start(self) -> None:
        log_event(logger, "collector.channel_start", channel=self.channel)

    def emit_runtime(self) -> None:
        log_event(
            logger,
            "collector.channel_runtime",
            channel=self.channel,
            runtime_sec=round(self.runtime_sec, 3),
        )

    def emit_summary(self) -> None:
        log_event(
            logger,
            "collector.channel_summary",
            channel=self.channel,
            runtime_sec=round(self.runtime_sec, 3),
            messages_scanned=self.messages_scanned,
            messages_fetched=self.messages_fetched,
            new_rows=self.new_rows_written,
            deduped_rows=self.deduped_rows,
            media_downloads=self.media_downloads,
            media_skipped_existing=self.media_skipped_existing,
            exceptions_count=self.exceptions_count,
        )
