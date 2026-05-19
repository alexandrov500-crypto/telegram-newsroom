from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from html import unescape

from bot.ingestion.rss import fetch_feed_items
from bot.observability.loop_diagnostics import track_sync_db
from bot.operations.repository import OperationsRepository

logger = logging.getLogger(__name__)

def _default_catalog() -> dict[str, str]:
    try:
        from bot.staging.feeds_config import load_staging_feed_catalog

        cat = load_staging_feed_catalog()
        if cat:
            return cat
    except Exception:
        pass
    return {
        "reuters": "https://feeds.reuters.com/reuters/worldNews",
        "ap": "https://rsshub.app/apnews/topics/apf-topnews",
        "bbc": "http://feeds.bbci.co.uk/news/world/rss.xml",
        "dw": "https://rss.dw.com/rdf/rss-en-world",
        "noisy_test": "https://feeds.bbci.co.uk/news/rss.xml",
    }


STAGING_FEED_CATALOG: dict[str, str] = _default_catalog()


@dataclass(frozen=True)
class FeedValidationResult:
    feed_url: str
    source_name: str
    items_fetched: int
    malformed: int
    duplicates: int
    reliability: float
    encoding_repairs: int
    error: str | None = None


class FeedValidationLayer:
    """Real-world noisy ingestion validation."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    @staticmethod
    def repair_encoding(text: str) -> tuple[str, int]:
        repairs = 0
        if not text:
            return text, 0
        try:
            fixed = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            if fixed != text:
                repairs += 1
                text = fixed
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        text = unescape(text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
        return text.strip(), repairs

    def validate_feed(self, feed_url: str, *, source_name: str) -> FeedValidationResult:
        malformed = 0
        encoding_repairs = 0
        error = None
        items: list = []
        try:
            with track_sync_db(f"feed_fetch:{source_name}"):
                items = fetch_feed_items(feed_url)
        except Exception as exc:
            error = str(exc)[:500]
            logger.warning("event=feed_fetch_failed url=%s error=%s", feed_url, error)

        seen_links: set[str] = set()
        duplicates = 0
        for item in items:
            title, repairs = self.repair_encoding(item.title)
            encoding_repairs += repairs
            if not title or len(title) < 3:
                malformed += 1
            if item.link in seen_links:
                duplicates += 1
            seen_links.add(item.link)

        duplicate_burst = 1 if duplicates > max(5, len(items) * 0.5) and len(items) > 3 else 0
        if duplicate_burst:
            try:
                from bot.observability.metrics import record_ingestion_pressure

                record_ingestion_pressure(source_name)
            except Exception:
                pass
        reliability = 0.5
        if error:
            reliability = max(0.1, reliability - 0.3)
        else:
            reliability = min(1.0, 0.4 + len(items) / 50.0)
        reliability -= malformed * 0.05
        reliability -= duplicate_burst * 0.15
        reliability = max(0.05, min(1.0, reliability))

        self._repo.upsert_feed_health(
            feed_url,
            source_name=source_name,
            reliability=reliability,
            malformed_delta=malformed,
            duplicate_burst=duplicate_burst,
            error=error,
            success=error is None,
        )
        try:
            from bot.observability.metrics import record_feed_validation

            record_feed_validation(source_name, reliability, malformed)
        except Exception:
            pass
        return FeedValidationResult(
            feed_url=feed_url,
            source_name=source_name,
            items_fetched=len(items),
            malformed=malformed,
            duplicates=duplicates,
            reliability=round(reliability, 4),
            encoding_repairs=encoding_repairs,
            error=error,
        )

    def validate_catalog(self, catalog: dict[str, str] | None = None) -> list[FeedValidationResult]:
        cat = catalog or _default_catalog()
        return [self.validate_feed(url, source_name=name) for name, url in cat.items()]

    async def validate_catalog_async(
        self,
        catalog: dict[str, str] | None = None,
    ) -> list[FeedValidationResult]:
        """Validate feeds without blocking the asyncio event loop."""
        cat = catalog or _default_catalog()

        async def _one(name: str, url: str) -> FeedValidationResult:
            return await asyncio.to_thread(self.validate_feed, url, source_name=name)

        return list(await asyncio.gather(*[_one(name, url) for name, url in cat.items()]))
