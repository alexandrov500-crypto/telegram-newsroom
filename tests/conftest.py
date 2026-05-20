from __future__ import annotations

import os
import tempfile
from pathlib import Path
from dataclasses import replace

import pytest

import scheduler.pipeline_lock as pipeline_lock
from app.config import Settings

pytest_plugins = ("tests.runtime_fixtures",)


@pytest.fixture(autouse=True)
def _isolate_ci_regression_env() -> None:
    """Prevent host/CI NEWSROOM_* skip lists from affecting deterministic unit tests."""
    keys = ("NEWSROOM_REGRESSION_SKIP_METRICS", "NEWSROOM_QUALIFICATION_SKIP_RUNTIME_KEYS")
    saved = {k: os.environ.pop(k, None) for k in keys}
    yield
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)


def minimal_test_settings(**overrides: object) -> Settings:
    """Valid Settings for unit tests (no real secrets, no network)."""
    _rt = Path(tempfile.gettempdir()) / f"newsroom_runtime_test_{os.getpid()}"
    base = Settings(
        openai_api_key="sk-test-key-for-unit-tests",
        openai_model="gpt-4.1-mini",
        openai_json_max_retries=3,
        openai_request_timeout_sec=90.0,
        openai_http_timeout_sec=120.0,
        openai_max_retries=2,
        max_post_chars=3500,
        max_cluster_posts=40,
        precluster_bucket_hours=6,
        raw_fetch_cap=300,
        telegram_api_id=123456,
        telegram_api_hash="testhash",
        telethon_session_string="test-session-string",
        telethon_session_path=None,
        telethon_op_max_attempts=4,
        bot_token="123456:ABCDEF-test-token",
        admin_user_id=1,
        target_channel_id=-1001234567890,
        source_channels=("@testchannel",),
        database_url="sqlite+aiosqlite:///:memory:",
        database_pool_size=5,
        database_max_overflow=10,
        redis_enabled=False,
        redis_url="redis://127.0.0.1:6379/0",
        job_queue_prefix="newsroom_test",
        worker_heartbeat_ttl_sec=90,
        health_http_port=0,
        health_http_bind="127.0.0.1",
        healthcheck_timeout_sec=60.0,
        telegram_http_timeout_sec=60.0,
        telegram_polling_enabled=True,
        runtime_degraded_after_n_failures=3,
        runtime_unavailable_after_n_minutes=30.0,
        runtime_recovery_stability_window_sec=120.0,
        ops_http_token="",
        worker_visibility_sec=120,
        worker_poll_interval_sec=0.5,
        worker_max_concurrency=2,
        worker_grace_shutdown_sec=15.0,
        worker_max_job_sec=120.0,
        worker_retry_deadline_sec=3600.0,
        worker_retry_jitter_ratio=0.12,
        worker_instance_id="test-instance",
        redis_transport_max_retries=5,
        redis_transport_backoff_sec=0.25,
        redis_transport_backoff_max_sec=8.0,
        runtime_queue_pending_warn=500,
        runtime_queue_processing_warn=50,
        runtime_queue_lag_warn_sec=600.0,
        runtime_success_stale_warn_sec=300.0,
        runtime_retry_storm_count=40,
        runtime_retry_storm_window_sec=60.0,
        runtime_active_job_warn_sec=120.0,
        runtime_queue_growth_warn_depth=2000,
        pipeline_interval_minutes=30,
        collect_messages_per_channel=40,
        channel_collect_delay_seconds=1.0,
        min_raw_posts_for_ai=3,
        draft_similarity_threshold=0.93,
        draft_dedupe_window_hours=72,
        retention_processed_raw_days=30,
        retention_rejected_draft_days=60,
        telegram_inter_chunk_delay_sec=0.35,
        log_max_field_len=480,
        log_level="INFO",
        dry_run=True,
        safe_mode=False,
        soak_test=False,
        send_startup_notification=False,
        send_recovery_notification=False,
        notification_rate_limit_minutes=30.0,
        startup_telegram_notify=False,
        diagnostics_interval_minutes=0,
        metrics_summary_interval_minutes=0,
        sqlite_analyze_interval_hours=0,
        sqlite_vacuum_interval_hours=0,
        anomaly_pipeline_slow_abs_sec=720.0,
        anomaly_pipeline_slow_vs_avg_multiplier=2.5,
        anomaly_duplicate_skip_streak=5,
        anomaly_cluster_size_ratio=0.92,
        anomaly_asyncio_tasks_warn=380,
        anomaly_memory_rss_bytes_warn=0,
        anomaly_telethon_reconnect_burst=6,
        anomaly_openai_failures_burst_delta=3,
        trend_ring_max_samples=24,
        trend_slow_multiplier=2.0,
        trend_publish_slow_multiplier=2.0,
        memory_trend_window=8,
        warn_task_count_trend=True,
        warn_rss_trend=True,
        warn_raw_posts_trend=True,
        warn_backlog_trend=True,
        quality_min_summary_chars=40,
        quality_low_uniqueness_ratio=0.18,
        quality_min_sources_ratio=0.25,
        operational_report_interval_hours=4,
        summary_style="neutral",
        cluster_min_lexical_jaccard=0.08,
        cluster_min_pair_last_jaccard=0.04,
        precluster_trim_bucket_multiplier=3,
        source_mentions_in_post=False,
        editorial_safety_enabled=True,
        headline_mode="none",
        digest_multi_post_enabled=False,
        digest_cohesion_trigger_below=0.11,
        quality_scoring_enabled=True,
        newsroom_timezone="UTC",
        channel_routing_rules_json="{}",
        editorial_policies_json="{}",
        runtime_state_dir=str(_rt),
        runtime_snapshots_max_count=64,
        runtime_snapshots_max_age_hours=168,
        runtime_snapshots_max_storage_bytes=52428800,
        runtime_event_flush_interval_sec=86400,
        deployment_profile="development",
        publish_channel_min_interval_sec=0.0,
        publish_burst_window_sec=30.0,
        publish_burst_max_messages=20,
        worker_retry_safe=False,
        publish_lock_strict=False,
        runtime_drift_monitor_enabled=False,
        scheduler_diagnostics_enabled=False,
        security_redaction_enabled=False,
    )
    if not overrides:
        return base
    return replace(base, **overrides)  # type: ignore[arg-type]


@pytest.fixture
def valid_settings() -> Settings:
    return minimal_test_settings()


@pytest.fixture(autouse=True)
def reset_pipeline_lock_singleton() -> None:
    """Isolate asyncio pipeline lock between tests (same process)."""
    with pipeline_lock._init_lock:
        pipeline_lock._async_lock = None
    yield
    with pipeline_lock._init_lock:
        pipeline_lock._async_lock = None


@pytest.fixture(autouse=True)
def reset_operational_runtime_buffers() -> None:
    from utils.operational_context import reset_operational_context_for_tests
    from utils.runtime_events import reset_runtime_events_for_tests
    from utils.runtime_state_store import reset_runtime_flush_clock_for_tests

    from publisher.publish_lock import reset_publish_locks_for_tests
    from publisher.publish_service import reset_idempotency_store_for_tests
    from publisher.rate_limit import reset_publish_rate_limiter_for_tests
    from utils.redis_client import reset_redis_client_for_tests
    from utils.structured_log import reset_log_event_id_sequence_for_tests
    from worker.job_queue import reset_job_queue_for_tests
    from worker.reliable_transport import reset_reliable_transport_for_tests
    from workers.state import reset_worker_runtime_state_for_tests
    from utils.reliability_diagnostics import reset_reliability_diagnostics_for_tests

    reset_reliability_diagnostics_for_tests()
    reset_publish_rate_limiter_for_tests()
    reset_publish_locks_for_tests()
    reset_idempotency_store_for_tests()
    reset_redis_client_for_tests()
    reset_job_queue_for_tests()
    reset_reliable_transport_for_tests()
    reset_worker_runtime_state_for_tests()
    reset_runtime_events_for_tests()
    reset_operational_context_for_tests()
    reset_log_event_id_sequence_for_tests()
    reset_runtime_flush_clock_for_tests()
    yield
