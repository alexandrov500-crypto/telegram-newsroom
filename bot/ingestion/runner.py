from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Sequence

from bot.ingestion.pipeline import IngestOutcome, ingest_news_item
from bot.ingestion.rss import fetch_feed_items
from bot.observability.loop_health import LoopIterationStats, record_rss_iteration
from bot.runtime.state import runtime_state
from bot.storage.cluster_repository import ClusterRepository
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.repository import LinkDedup
from bot.editorial.agent_service import EditorialAgentService
from bot.editorial.story_memory import StoryMemoryService
from bot.signals.signal_service import SignalIntelligenceService
from bot.adaptive.service import AdaptiveOperationsService
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.entity_repository import EntityRepository
from bot.observability.registry import ObservabilityRegistry
from bot.storage.localization_repository import LocalizationRepository
from bot.storage.source_repository import SourceRepository

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 60
FEED_TIMEOUT_SEC = float(os.getenv("RSS_FEED_TIMEOUT_SEC", "20"))
FEED_CONCURRENCY = max(1, int(os.getenv("RSS_FEED_CONCURRENCY", "2")))
ITEM_YIELD_EVERY = max(1, int(os.getenv("RSS_ITEM_YIELD_EVERY", "5")))


async def _fetch_feed_timed(feed_url: str) -> tuple[str, list, float]:
    """Fetch one feed in a thread with timeout; returns (url, items, duration)."""
    started = time.perf_counter()
    try:
        items = await asyncio.wait_for(
            asyncio.to_thread(fetch_feed_items, feed_url),
            timeout=FEED_TIMEOUT_SEC,
        )
        return feed_url, items, time.perf_counter() - started
    except asyncio.TimeoutError:
        logger.warning(
            "event=rss_feed_timeout feed=%r timeout_sec=%s",
            feed_url,
            FEED_TIMEOUT_SEC,
        )
        return feed_url, [], time.perf_counter() - started
    except Exception:
        logger.exception("event=ingestion_feed_failed source=%r", feed_url)
        return feed_url, [], time.perf_counter() - started


async def run_ingestion_loop(
    feed_urls: Sequence[str],
    dedup: LinkDedup,
    editorial: EditorialRepository,
    clusters: ClusterRepository,
    sources: SourceRepository | None = None,
    entities: EntityRepository | None = None,
    analytics: AnalyticsRepository | None = None,
    agents: EditorialAgentService | None = None,
    localizations: LocalizationRepository | None = None,
    story_memory: StoryMemoryService | None = None,
    signal_intel: SignalIntelligenceService | None = None,
    adaptive: AdaptiveOperationsService | None = None,
    registry: ObservabilityRegistry | None = None,
    feed_resilience: object | None = None,
    *,
    interval_sec: int = DEFAULT_INTERVAL_SEC,
) -> None:
    """Periodically fetch RSS feeds and enqueue new items. Never blocks the event loop."""
    if not feed_urls:
        logger.warning(
            "event=ingestion_disabled reason='RSS_FEEDS empty; loop idle'",
        )

    sem = asyncio.Semaphore(FEED_CONCURRENCY)

    async def _fetch_one(url: str) -> tuple[str, list, float]:
        async with sem:
            if feed_resilience is not None:
                verdict = feed_resilience.evaluate_feed(url, source_name=url)
                if not verdict.allowed:
                    logger.info(
                        "event=feed_skipped_resilience feed=%r reason=%s",
                        url,
                        verdict.reason,
                    )
                    return url, [], 0.0
            return await _fetch_feed_timed(url)

    while True:
        cycle_started = time.perf_counter()
        cycle_error: str | None = None
        network_duration = 0.0
        db_write_duration = 0.0
        longest_fetch = 0.0
        longest_url = ""
        new_items_count = 0
        skipped_duplicates = 0
        enqueued_count = 0
        cluster_matched_count = 0

        try:
            if runtime_state.ingestion_paused:
                logger.info("event=ingestion_cycle_paused")
                try:
                    from bot.observability.loop_registry import get_loop_registry

                    get_loop_registry().heartbeat("rss-ingestion", 0.0)
                except Exception:
                    pass
                await asyncio.sleep(
                    interval_sec * max(1.0, runtime_state.ingestion_interval_multiplier),
                )
                continue

            logger.info("event=ingestion_cycle_start feed_count=%d", len(feed_urls))

            feed_results = await asyncio.gather(
                *[_fetch_one(url) for url in feed_urls],
                return_exceptions=False,
            )

            for feed_url, items, fetch_dur in feed_results:
                network_duration += fetch_dur
                if fetch_dur > longest_fetch:
                    longest_fetch = fetch_dur
                    longest_url = feed_url

                if feed_resilience is not None and feed_resilience.record_duplicate_burst(
                    feed_url,
                ):
                    logger.info("event=feed_burst_suppressed feed=%r", feed_url)
                    continue

                for idx, item in enumerate(items):
                    try:
                        from bot.editorial.flow_health.funnel import record_funnel

                        record_funnel("FETCHED")
                    except Exception:
                        pass
                    if idx > 0 and idx % ITEM_YIELD_EVERY == 0:
                        await asyncio.sleep(0)
                        try:
                            from bot.observability.loop_registry import get_loop_registry

                            get_loop_registry().heartbeat(
                                "rss-ingestion",
                                time.perf_counter() - cycle_started,
                            )
                        except Exception:
                            pass

                    item_started = time.perf_counter()
                    try:
                        new_items_count += 1
                        result = await ingest_news_item(
                            item,
                            dedup=dedup,
                            editorial=editorial,
                            clusters=clusters,
                            sources=sources,
                            entities=entities,
                            analytics=analytics,
                            agents=agents,
                            localizations=localizations,
                            story_memory=story_memory,
                            signal_intel=signal_intel,
                            adaptive=adaptive,
                        )
                        db_write_duration += time.perf_counter() - item_started
                        if result.outcome == IngestOutcome.ENQUEUED:
                            enqueued_count += 1
                        elif result.outcome == IngestOutcome.CLUSTER_MATCHED:
                            cluster_matched_count += 1
                        elif result.outcome in (
                            IngestOutcome.DUPLICATE_SKIPPED,
                            IngestOutcome.CLUSTER_DUPLICATE,
                        ):
                            skipped_duplicates += 1
                    except Exception:
                        db_write_duration += time.perf_counter() - item_started
                        logger.exception(
                            "event=ingestion_item_failed link=%r",
                            item.link,
                        )

            logger.info("event=ingestion_new_items_count count=%d", new_items_count)
            logger.info("event=ingestion_enqueued_count count=%d", enqueued_count)
            logger.info(
                "event=ingestion_cluster_matched_count count=%d",
                cluster_matched_count,
            )
            logger.info(
                "event=ingestion_skipped_duplicates count=%d",
                skipped_duplicates,
            )
        except asyncio.CancelledError:
            logger.info("event=ingestion_loop_stopped")
            raise
        except Exception:
            cycle_error = "cycle_failed"
            logger.exception("event=ingestion_cycle_failed")
        finally:
            iteration_duration = time.perf_counter() - cycle_started
            record_rss_iteration(
                LoopIterationStats(
                    loop_name="rss-ingestion",
                    iteration_duration=iteration_duration,
                    feed_count=len(feed_urls),
                    article_count=new_items_count,
                    network_duration=network_duration,
                    db_write_duration=db_write_duration,
                    longest_feed_fetch=longest_fetch,
                    longest_feed_url=longest_url,
                ),
            )
            try:
                from bot.observability.loop_registry import get_loop_registry

                get_loop_registry().heartbeat(
                    "rss-ingestion",
                    iteration_duration,
                    error=cycle_error,
                )
            except Exception:
                pass

        if registry is not None:
            await registry.mark_rss_cycle()

        sleep_sec = interval_sec * max(1.0, runtime_state.ingestion_interval_multiplier)
        await asyncio.sleep(sleep_sec)
