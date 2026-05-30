"""In-process collect progress for partial-commit observability."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


@dataclass
class CollectProgress:
    new_rows_total: int = 0
    channels_processed: int = 0
    planned_total: int = 0
    processed_channels: list[str] = field(default_factory=list)

    def record_channel(self, channel: str, new_rows: int, *, commit_sec: float = 0.0) -> None:
        self.channels_processed += 1
        self.new_rows_total += int(new_rows)
        self.processed_channels.append(channel)
        log_event(
            logger,
            "collector.channels_processed",
            channel=channel,
            new_rows=int(new_rows),
            processed=self.channels_processed,
            planned=self.planned_total,
        )
        if new_rows > 0:
            log_event(
                logger,
                "collector.partial_commit",
                channel=channel,
                new_rows=int(new_rows),
                total_new_rows=self.new_rows_total,
                commit_sec=round(commit_sec, 4),
            )

    def channels_skipped_count(self) -> int:
        if self.planned_total <= 0:
            return 0
        return max(0, self.planned_total - self.channels_processed)
