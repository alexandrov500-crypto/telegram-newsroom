from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from utils.database_url import normalize_async_database_url

load_dotenv()


def _parse_channels(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    return [p for p in parts if p]


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    openai_api_key: str
    openai_model: str
    openai_json_max_retries: int
    openai_request_timeout_sec: float
    openai_http_timeout_sec: float
    openai_max_retries: int
    max_post_chars: int
    max_cluster_posts: int
    precluster_bucket_hours: int
    raw_fetch_cap: int
    telegram_api_id: int
    telegram_api_hash: str
    telethon_session_string: str | None
    telethon_session_path: str | None
    telethon_op_max_attempts: int
    bot_token: str
    admin_user_id: int
    target_channel_id: int
    source_channels: tuple[str, ...]
    database_url: str
    database_pool_size: int
    database_max_overflow: int
    redis_enabled: bool
    redis_url: str
    job_queue_prefix: str
    worker_heartbeat_ttl_sec: int
    health_http_port: int
    health_http_bind: str
    healthcheck_timeout_sec: float
    telegram_http_timeout_sec: float
    telegram_polling_enabled: bool
    runtime_degraded_after_n_failures: int
    runtime_unavailable_after_n_minutes: float
    runtime_recovery_stability_window_sec: float
    # Optional shared secret for /ops* and /metrics when set (empty = no auth).
    ops_http_token: str
    pipeline_interval_minutes: int
    collect_messages_per_channel: int
    channel_collect_delay_seconds: float
    min_raw_posts_for_ai: int
    draft_similarity_threshold: float
    draft_dedupe_window_hours: int
    retention_processed_raw_days: int
    retention_rejected_draft_days: int
    telegram_inter_chunk_delay_sec: float
    log_max_field_len: int
    log_level: str
    dry_run: bool
    safe_mode: bool
    soak_test: bool
    send_startup_notification: bool
    send_recovery_notification: bool
    notification_rate_limit_minutes: float
    startup_telegram_notify: bool  # deprecated alias → send_startup_notification
    diagnostics_interval_minutes: int
    metrics_summary_interval_minutes: int
    sqlite_analyze_interval_hours: int
    sqlite_vacuum_interval_hours: int
    # observability / soak anomaly knobs
    anomaly_pipeline_slow_abs_sec: float
    anomaly_pipeline_slow_vs_avg_multiplier: float
    anomaly_duplicate_skip_streak: int
    anomaly_cluster_size_ratio: float
    anomaly_asyncio_tasks_warn: int
    anomaly_memory_rss_bytes_warn: int
    anomaly_telethon_reconnect_burst: int
    anomaly_openai_failures_burst_delta: int
    trend_ring_max_samples: int
    trend_slow_multiplier: float
    trend_publish_slow_multiplier: float
    memory_trend_window: int
    warn_task_count_trend: bool
    warn_rss_trend: bool
    warn_raw_posts_trend: bool
    warn_backlog_trend: bool
    quality_min_summary_chars: int
    quality_low_uniqueness_ratio: float
    quality_min_sources_ratio: float
    operational_report_interval_hours: int
    # Editorial / newsroom output (prompt + precluster tuning; no pipeline blocking)
    summary_style: str
    cluster_min_lexical_jaccard: float
    cluster_min_pair_last_jaccard: float
    precluster_trim_bucket_multiplier: int
    source_mentions_in_post: bool
    editorial_safety_enabled: bool
    headline_mode: str
    digest_multi_post_enabled: bool
    digest_cohesion_trigger_below: float
    quality_scoring_enabled: bool
    editorial_scoring_timeout_sec: float
    # Newsroom operator UX (timezone label + optional JSON routing map: tag/category -> channel id)
    newsroom_timezone: str
    channel_routing_rules_json: str
    # Optional JSON object merged over ``RUNTIME_STATE_DIR/editorial_policies.json`` (per-channel policy).
    editorial_policies_json: str
    # Persistent operational snapshots (local JSON, no secrets)
    runtime_state_dir: str
    runtime_snapshots_max_count: int
    runtime_snapshots_max_age_hours: int
    runtime_snapshots_max_storage_bytes: int
    runtime_event_flush_interval_sec: int
    deployment_profile: str
    publish_channel_min_interval_sec: float
    publish_burst_window_sec: float
    publish_burst_max_messages: int
    worker_visibility_sec: int
    worker_poll_interval_sec: float
    worker_max_concurrency: int
    worker_grace_shutdown_sec: float
    worker_max_job_sec: float
    worker_retry_deadline_sec: float
    worker_retry_jitter_ratio: float
    worker_instance_id: str
    # Redis transport resilience (bounded retries; outer dequeue loop stays hot)
    redis_transport_max_retries: int
    redis_transport_backoff_sec: float
    redis_transport_backoff_max_sec: float
    # Runtime diagnostics / watchdogs (warnings only; no process control)
    runtime_queue_pending_warn: int
    runtime_queue_processing_warn: int
    runtime_queue_lag_warn_sec: float
    runtime_success_stale_warn_sec: float
    runtime_retry_storm_count: int
    runtime_retry_storm_window_sec: float
    runtime_active_job_warn_sec: float
    runtime_queue_growth_warn_depth: int
    # v1.1 reliability (opt-in; default preserves v1.0.0 behavior)
    worker_retry_safe: bool
    publish_lock_strict: bool
    # v1.3 resilience (opt-in; default off)
    runtime_drift_monitor_enabled: bool
    scheduler_diagnostics_enabled: bool
    security_redaction_enabled: bool


def load_settings() -> Settings:
    openai_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required")

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("BOT_TOKEN is required")

    session_path = os.getenv("TELETHON_SESSION_PATH", "").strip() or None
    session_string = os.getenv("TELETHON_SESSION_STRING", "").strip() or None
    if not session_path and not session_string:
        raise RuntimeError("At least one of TELETHON_SESSION_PATH or TELETHON_SESSION_STRING is required")

    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
    if not api_id_raw:
        raise RuntimeError("TELEGRAM_API_ID is required")
    telegram_api_id = int(api_id_raw)

    telegram_api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    if not telegram_api_hash:
        raise RuntimeError("TELEGRAM_API_HASH is required")

    admin_raw = os.getenv("ADMIN_USER_ID", "").strip()
    if not admin_raw:
        raise RuntimeError("ADMIN_USER_ID is required")
    admin_user_id = int(admin_raw)

    target_raw = os.getenv("TARGET_CHANNEL_ID", "").strip()
    if not target_raw:
        raise RuntimeError("TARGET_CHANNEL_ID is required")
    target_channel_id = int(target_raw)

    channels_raw = os.getenv("SOURCE_CHANNELS", "").strip()
    if not channels_raw:
        raise RuntimeError("SOURCE_CHANNELS is required (comma-separated)")
    channels = tuple(_parse_channels(channels_raw))
    if not channels:
        raise RuntimeError("SOURCE_CHANNELS must contain at least one channel")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        db_path = Path(os.getenv("SQLITE_PATH", "./newsroom.db")).resolve()
        database_url = f"sqlite+aiosqlite:///{db_path}"
    database_url = normalize_async_database_url(database_url)

    db_pool = int(os.getenv("DATABASE_POOL_SIZE", "5"))
    db_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))

    redis_enabled = _env_bool("REDIS_ENABLED", "false")
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0").strip()
    job_queue_prefix = os.getenv("NEWSROOM_QUEUE_PREFIX", "newsroom").strip() or "newsroom"
    worker_hb_ttl = int(os.getenv("WORKER_HEARTBEAT_TTL_SEC", "90"))
    health_http_port = int(os.getenv("HEALTH_HTTP_PORT", "0"))
    health_http_bind = os.getenv("HEALTH_HTTP_BIND", "0.0.0.0").strip() or "0.0.0.0"
    ops_http_token = os.getenv("OPS_HTTP_TOKEN", "").strip()

    worker_vis = int(os.getenv("WORKER_VISIBILITY_SEC", "120"))
    worker_poll = float(os.getenv("WORKER_POLL_INTERVAL_SEC", "1.0"))
    worker_conc = int(os.getenv("WORKER_MAX_CONCURRENCY", "2"))
    worker_grace = float(os.getenv("WORKER_GRACE_SHUTDOWN_SEC", "30"))
    worker_max_job = float(os.getenv("WORKER_MAX_JOB_SEC", "900"))
    worker_retry_dead = float(os.getenv("WORKER_RETRY_DEADLINE_SEC", "3600"))
    worker_jitter = float(os.getenv("WORKER_RETRY_JITTER_RATIO", "0.12"))
    worker_iid = os.getenv("WORKER_INSTANCE_ID", "").strip() or f"{socket.gethostname()}:{os.getpid()}"

    redis_tr_max = int(os.getenv("REDIS_TRANSPORT_MAX_RETRIES", "5"))
    redis_tr_back = float(os.getenv("REDIS_TRANSPORT_BACKOFF_SEC", "0.25"))
    redis_tr_cap = float(os.getenv("REDIS_TRANSPORT_BACKOFF_MAX_SEC", "8"))
    rt_q_pending = int(os.getenv("RUNTIME_QUEUE_PENDING_WARN", "500"))
    rt_q_proc = int(os.getenv("RUNTIME_QUEUE_PROCESSING_WARN", "50"))
    rt_lag = float(os.getenv("RUNTIME_QUEUE_LAG_WARN_SEC", "600"))
    rt_stale = float(os.getenv("RUNTIME_SUCCESS_STALE_WARN_SEC", "300"))
    rt_storm_n = int(os.getenv("RUNTIME_RETRY_STORM_COUNT", "40"))
    rt_storm_w = float(os.getenv("RUNTIME_RETRY_STORM_WINDOW_SEC", "60"))
    rt_active = float(os.getenv("RUNTIME_ACTIVE_JOB_WARN_SEC", "120"))
    rt_growth = int(os.getenv("RUNTIME_QUEUE_GROWTH_WARN_DEPTH", "2000"))
    worker_retry_safe = _env_bool("WORKER_RETRY_SAFE", "false")
    publish_lock_strict = _env_bool("PUBLISH_LOCK_STRICT", "false")
    runtime_drift_monitor_enabled = _env_bool("RUNTIME_DRIFT_MONITOR", "false")
    scheduler_diagnostics_enabled = _env_bool("SCHEDULER_DIAGNOSTICS", "false")
    security_redaction_enabled = _env_bool("SECURITY_REDACTION", "false")

    pipeline_interval = int(os.getenv("PIPELINE_INTERVAL_MINUTES", "30"))
    collect_limit = int(os.getenv("COLLECT_MESSAGES_PER_CHANNEL", "40"))
    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    openai_json_max_retries = int(os.getenv("OPENAI_JSON_MAX_RETRIES", "3"))
    telethon_op_max_attempts = int(os.getenv("TELETHON_OP_MAX_ATTEMPTS", "4"))
    channel_collect_delay = float(os.getenv("CHANNEL_COLLECT_DELAY_SECONDS", "1.25"))
    min_raw_posts = int(os.getenv("MIN_RAW_POSTS_FOR_AI", "3"))
    similarity = float(os.getenv("DRAFT_SIMILARITY_THRESHOLD", "0.93"))
    dedupe_hours = int(os.getenv("DRAFT_DEDUPE_WINDOW_HOURS", "72"))

    max_post_chars = int(os.getenv("MAX_POST_CHARS", "3500"))
    max_cluster_posts = int(os.getenv("MAX_CLUSTER_POSTS", "40"))
    precluster_bucket_hours = int(os.getenv("PRECLUSTER_BUCKET_HOURS", "6"))
    raw_fetch_cap = int(os.getenv("RAW_FETCH_CAP", "300"))

    openai_request_timeout = float(os.getenv("OPENAI_REQUEST_TIMEOUT_SEC", "90"))
    openai_http_timeout = float(os.getenv("OPENAI_HTTP_TIMEOUT_SEC", "120"))
    openai_max_retries = int(os.getenv("OPENAI_HTTP_MAX_RETRIES", "2"))
    healthcheck_timeout = float(os.getenv("HEALTHCHECK_TIMEOUT_SEC", "60"))
    telegram_http_timeout = float(os.getenv("TELEGRAM_HTTP_TIMEOUT_SEC", "60"))

    retention_raw = int(os.getenv("RETENTION_PROCESSED_RAW_DAYS", "30"))
    retention_rej = int(os.getenv("RETENTION_REJECTED_DRAFT_DAYS", "60"))
    chunk_delay = float(os.getenv("TELEGRAM_INTER_CHUNK_DELAY_SEC", "0.35"))
    log_max_field = int(os.getenv("LOG_MAX_FIELD_LEN", "480"))

    diag_min = int(os.getenv("DIAGNOSTICS_INTERVAL_MINUTES", "0"))
    metrics_sum_min = int(os.getenv("METRICS_SUMMARY_INTERVAL_MINUTES", "0"))
    sqlite_analyze_h = int(os.getenv("SQLITE_ANALYZE_INTERVAL_HOURS", "0"))
    sqlite_vacuum_h = int(os.getenv("SQLITE_VACUUM_INTERVAL_HOURS", "0"))

    ap_slow_abs = float(os.getenv("ANOMALY_PIPELINE_SLOW_ABS_SEC", "720"))
    ap_slow_mult = float(os.getenv("ANOMALY_PIPELINE_SLOW_VS_AVG_MULTIPLIER", "2.5"))
    dup_streak = int(os.getenv("ANOMALY_DUPLICATE_SKIP_STREAK", "5"))
    cluster_ratio = float(os.getenv("ANOMALY_CLUSTER_SIZE_RATIO", "0.92"))
    asyncio_warn = int(os.getenv("ANOMALY_ASYNCIO_TASKS_WARN", "380"))
    mem_rss_warn = int(os.getenv("ANOMALY_MEMORY_RSS_BYTES_WARN", "0"))
    tele_burst = int(os.getenv("ANOMALY_TELETHON_RECONNECT_BURST", "6"))
    oai_burst = int(os.getenv("ANOMALY_OPENAI_FAILURES_BURST_DELTA", "3"))
    trend_ring = int(os.getenv("TREND_RING_MAX_SAMPLES", "24"))
    trend_mult = float(os.getenv("TREND_SLOW_MULTIPLIER", "2.0"))
    trend_pub_mult = float(os.getenv("TREND_PUBLISH_SLOW_MULTIPLIER", "2.0"))
    mem_win = int(os.getenv("MEMORY_TREND_WINDOW", "8"))
    q_min_chars = int(os.getenv("QUALITY_MIN_SUMMARY_CHARS", "40"))
    q_uniq = float(os.getenv("QUALITY_LOW_UNIQUENESS_RATIO", "0.18"))
    q_src_ratio = float(os.getenv("QUALITY_MIN_SOURCES_RATIO", "0.25"))
    op_rep_h = int(os.getenv("OPERATIONAL_REPORT_INTERVAL_HOURS", "4"))

    cluster_min_lex = float(os.getenv("CLUSTER_MIN_LEXICAL_JACCARD", "0.08"))
    cluster_min_last = float(os.getenv("CLUSTER_MIN_PAIR_LAST_JACCARD", "0.04"))
    trim_mult = int(os.getenv("PRECLUSTER_TRIM_BUCKET_MULTIPLIER", "3"))
    digest_coh = float(os.getenv("DIGEST_COHESION_TRIGGER_BELOW", "0.11"))

    newsroom_tz = os.getenv("NEWSROOM_TIMEZONE", "UTC").strip() or "UTC"
    routing_rules = os.getenv("CHANNEL_ROUTING_RULES_JSON", "").strip() or "{}"
    editorial_policies_json = os.getenv("EDITORIAL_POLICIES_JSON", "").strip() or "{}"

    runtime_state_dir = os.getenv("RUNTIME_STATE_DIR", "var/runtime").strip() or "var/runtime"
    rt_max_count = int(os.getenv("RUNTIME_SNAPSHOTS_MAX_COUNT", "64"))
    rt_max_age_h = int(os.getenv("RUNTIME_SNAPSHOTS_MAX_AGE_HOURS", "168"))
    rt_max_mb = int(os.getenv("RUNTIME_SNAPSHOTS_MAX_STORAGE_MB", "50"))
    rt_flush_sec = int(os.getenv("RUNTIME_EVENT_FLUSH_INTERVAL_SEC", "600"))

    os.environ.setdefault("LOG_MAX_FIELD_LEN", str(max(120, min(log_max_field, 4000))))

    soak = _env_bool("SOAK_TEST", "false")
    safe_mode = _env_bool("NEWSROOM_SAFE_MODE", "false")
    _startup_notify_raw = os.getenv("SEND_STARTUP_NOTIFICATION", "").strip()
    if _startup_notify_raw:
        send_startup_notification = _env_bool("SEND_STARTUP_NOTIFICATION", "true")
    else:
        send_startup_notification = _env_bool("TELEGRAM_STARTUP_NOTIFY", "false")
    send_recovery_notification = _env_bool("SEND_RECOVERY_NOTIFICATION", "false")
    notification_rate_limit_min = float(os.getenv("NOTIFICATION_RATE_LIMIT_MINUTES", "30"))

    if soak and diag_min == 0:
        diag_min = 30
    if soak and metrics_sum_min == 0:
        metrics_sum_min = diag_min

    from ai.editorial import normalize_headline_mode, normalize_summary_style

    summary_style = normalize_summary_style(os.getenv("SUMMARY_STYLE", "neutral"))
    headline_mode = normalize_headline_mode(os.getenv("HEADLINE_MODE", "none"))

    profile_raw = os.getenv("APP_DEPLOYMENT_PROFILE", os.getenv("NEWSROOM_PROFILE", "development")).strip().lower()
    if profile_raw not in ("development", "staging", "production"):
        profile_raw = "development"

    pub_interval_env = os.getenv("PUBLISH_CHANNEL_MIN_INTERVAL_SEC", "").strip()
    burst_win_env = os.getenv("PUBLISH_BURST_WINDOW_SEC", "").strip()
    burst_max_env = os.getenv("PUBLISH_BURST_MAX_MESSAGES", "").strip()

    defaults_by_profile = {
        "development": (0.12, 30.0, 10),
        "staging": (0.45, 60.0, 6),
        "production": (1.25, 120.0, 4),
    }
    dflt_min, dflt_win, dflt_burst = defaults_by_profile[profile_raw]
    publish_min_interval = float(pub_interval_env) if pub_interval_env else dflt_min
    publish_burst_window = float(burst_win_env) if burst_win_env else dflt_win
    publish_burst_max = int(burst_max_env) if burst_max_env else dflt_burst

    if profile_raw == "staging":
        chunk_delay = max(chunk_delay, 0.25)
        channel_collect_delay = max(channel_collect_delay, 0.75)
    elif profile_raw == "production":
        if log_level == "DEBUG":
            log_level = "INFO"
        chunk_delay = max(chunk_delay, 0.45)
        channel_collect_delay = max(channel_collect_delay, 1.0)
        retention_raw = max(retention_raw, 14)
        retention_rej = max(retention_rej, 30)
        if diag_min == 0 and not soak:
            diag_min = 15
        if metrics_sum_min == 0 and not soak:
            metrics_sum_min = 30
        publish_min_interval = max(publish_min_interval, 0.75)
        publish_burst_max = min(publish_burst_max, 6)
        publish_burst_max = max(2, publish_burst_max)

    publish_min_interval = max(0.0, min(publish_min_interval, 300.0))
    publish_burst_window = max(5.0, min(publish_burst_window, 3600.0))
    publish_burst_max = max(1, min(publish_burst_max, 50))

    return Settings(
        openai_api_key=openai_api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip(),
        openai_json_max_retries=max(1, min(openai_json_max_retries, 8)),
        openai_request_timeout_sec=max(15.0, min(openai_request_timeout, 600.0)),
        openai_http_timeout_sec=max(20.0, min(openai_http_timeout, 600.0)),
        openai_max_retries=max(0, min(openai_max_retries, 5)),
        max_post_chars=max(500, min(max_post_chars, 12000)),
        max_cluster_posts=max(3, min(max_cluster_posts, 120)),
        precluster_bucket_hours=max(1, min(precluster_bucket_hours, 168)),
        raw_fetch_cap=max(50, min(raw_fetch_cap, 2000)),
        telegram_api_id=telegram_api_id,
        telegram_api_hash=telegram_api_hash,
        telethon_session_string=session_string,
        telethon_session_path=session_path,
        telethon_op_max_attempts=max(1, min(telethon_op_max_attempts, 12)),
        bot_token=bot_token,
        admin_user_id=admin_user_id,
        target_channel_id=target_channel_id,
        source_channels=channels,
        database_url=database_url,
        database_pool_size=max(1, min(db_pool, 64)),
        database_max_overflow=max(0, min(db_overflow, 128)),
        redis_enabled=redis_enabled,
        redis_url=redis_url,
        job_queue_prefix=job_queue_prefix[:120],
        worker_heartbeat_ttl_sec=max(15, min(worker_hb_ttl, 3600)),
        health_http_port=max(0, min(health_http_port, 65535)),
        health_http_bind=health_http_bind,
        healthcheck_timeout_sec=max(10.0, min(healthcheck_timeout, 300.0)),
        telegram_http_timeout_sec=max(10.0, min(telegram_http_timeout, 300.0)),
        telegram_polling_enabled=_env_bool("TELEGRAM_POLLING_ENABLED", "true"),
        runtime_degraded_after_n_failures=max(
            1, int(os.getenv("RUNTIME_DEGRADED_AFTER_N_FAILURES", "3"))
        ),
        runtime_unavailable_after_n_minutes=max(
            1.0, float(os.getenv("RUNTIME_UNAVAILABLE_AFTER_N_MINUTES", "30"))
        ),
        runtime_recovery_stability_window_sec=max(
            10.0, float(os.getenv("RUNTIME_RECOVERY_STABILITY_WINDOW_SEC", "120"))
        ),
        ops_http_token=ops_http_token[:512],
        pipeline_interval_minutes=max(1, pipeline_interval),
        collect_messages_per_channel=max(1, min(collect_limit, 200)),
        channel_collect_delay_seconds=max(0.0, min(channel_collect_delay, 60.0)),
        min_raw_posts_for_ai=max(1, min(min_raw_posts, 500)),
        draft_similarity_threshold=max(0.5, min(similarity, 1.0)),
        draft_dedupe_window_hours=max(1, min(dedupe_hours, 24 * 30)),
        retention_processed_raw_days=max(0, min(retention_raw, 3650)),
        retention_rejected_draft_days=max(0, min(retention_rej, 3650)),
        telegram_inter_chunk_delay_sec=max(0.0, min(chunk_delay, 5.0)),
        log_max_field_len=max(120, min(log_max_field, 4000)),
        log_level=log_level,
        dry_run=_env_bool("DRY_RUN", "false"),
        safe_mode=safe_mode,
        soak_test=soak,
        send_startup_notification=send_startup_notification,
        send_recovery_notification=send_recovery_notification,
        notification_rate_limit_minutes=max(1.0, min(notification_rate_limit_min, 24 * 60.0)),
        startup_telegram_notify=send_startup_notification,
        diagnostics_interval_minutes=max(0, min(diag_min, 24 * 60)),
        metrics_summary_interval_minutes=max(0, min(metrics_sum_min, 24 * 60)),
        sqlite_analyze_interval_hours=max(0, min(sqlite_analyze_h, 24 * 30)),
        sqlite_vacuum_interval_hours=max(0, min(sqlite_vacuum_h, 24 * 120)),
        anomaly_pipeline_slow_abs_sec=max(60.0, min(ap_slow_abs, 86400.0)),
        anomaly_pipeline_slow_vs_avg_multiplier=max(1.2, min(ap_slow_mult, 10.0)),
        anomaly_duplicate_skip_streak=max(2, min(dup_streak, 500)),
        anomaly_cluster_size_ratio=max(0.5, min(cluster_ratio, 1.0)),
        anomaly_asyncio_tasks_warn=max(0, min(asyncio_warn, 50000)),
        anomaly_memory_rss_bytes_warn=max(0, min(mem_rss_warn, 2**40)),
        anomaly_telethon_reconnect_burst=max(1, min(tele_burst, 5000)),
        anomaly_openai_failures_burst_delta=max(1, min(oai_burst, 500)),
        trend_ring_max_samples=max(5, min(trend_ring, 256)),
        trend_slow_multiplier=max(1.1, min(trend_mult, 8.0)),
        trend_publish_slow_multiplier=max(1.1, min(trend_pub_mult, 8.0)),
        memory_trend_window=max(3, min(mem_win, 48)),
        warn_task_count_trend=_env_bool("WARN_TASK_COUNT_TREND", "true"),
        warn_rss_trend=_env_bool("WARN_RSS_TREND", "true"),
        warn_raw_posts_trend=_env_bool("WARN_RAW_POSTS_TREND", "true"),
        warn_backlog_trend=_env_bool("WARN_BACKLOG_TREND", "true"),
        quality_min_summary_chars=max(10, min(q_min_chars, 500)),
        quality_low_uniqueness_ratio=max(0.05, min(q_uniq, 0.95)),
        quality_min_sources_ratio=max(0.05, min(q_src_ratio, 1.0)),
        operational_report_interval_hours=max(0, min(op_rep_h, 24 * 14)),
        summary_style=summary_style,
        cluster_min_lexical_jaccard=max(0.02, min(cluster_min_lex, 0.5)),
        cluster_min_pair_last_jaccard=max(0.0, min(cluster_min_last, 0.5)),
        precluster_trim_bucket_multiplier=max(2, min(trim_mult, 20)),
        source_mentions_in_post=_env_bool("SOURCE_MENTIONS_IN_POST", "false"),
        editorial_safety_enabled=_env_bool("EDITORIAL_SAFETY", "true"),
        headline_mode=headline_mode,
        digest_multi_post_enabled=_env_bool("DIGEST_MULTI_POST", "false"),
        digest_cohesion_trigger_below=max(0.02, min(digest_coh, 0.95)),
        quality_scoring_enabled=_env_bool("QUALITY_SCORING_ENABLED", "true"),
        editorial_scoring_timeout_sec=max(
            0.5,
            min(float(os.getenv("EDITORIAL_SCORING_TIMEOUT_SEC", "2.0")), 30.0),
        ),
        newsroom_timezone=newsroom_tz,
        channel_routing_rules_json=routing_rules,
        editorial_policies_json=editorial_policies_json,
        runtime_state_dir=runtime_state_dir,
        runtime_snapshots_max_count=max(4, min(rt_max_count, 500)),
        runtime_snapshots_max_age_hours=max(1, min(rt_max_age_h, 24 * 90)),
        runtime_snapshots_max_storage_bytes=max(1_048_576, min(rt_max_mb * 1024 * 1024, 2_147_483_647)),
        runtime_event_flush_interval_sec=max(60, min(rt_flush_sec, 86_400)),
        deployment_profile=profile_raw,
        publish_channel_min_interval_sec=publish_min_interval,
        publish_burst_window_sec=publish_burst_window,
        publish_burst_max_messages=publish_burst_max,
        worker_visibility_sec=max(5, min(worker_vis, 86400)),
        worker_poll_interval_sec=max(0.05, min(worker_poll, 30.0)),
        worker_max_concurrency=max(1, min(worker_conc, 64)),
        worker_grace_shutdown_sec=max(5.0, min(worker_grace, 600.0)),
        worker_max_job_sec=max(5.0, min(worker_max_job, 86400.0)),
        worker_retry_deadline_sec=max(10.0, min(worker_retry_dead, 86400.0 * 7)),
        worker_retry_jitter_ratio=max(0.0, min(worker_jitter, 0.5)),
        worker_instance_id=worker_iid[:200],
        redis_transport_max_retries=max(1, min(redis_tr_max, 30)),
        redis_transport_backoff_sec=max(0.05, min(redis_tr_back, 30.0)),
        redis_transport_backoff_max_sec=max(0.5, min(redis_tr_cap, 120.0)),
        runtime_queue_pending_warn=max(10, min(rt_q_pending, 1_000_000)),
        runtime_queue_processing_warn=max(1, min(rt_q_proc, 10_000)),
        runtime_queue_lag_warn_sec=max(30.0, min(rt_lag, 86400.0 * 7)),
        runtime_success_stale_warn_sec=max(30.0, min(rt_stale, 86400.0)),
        runtime_retry_storm_count=max(5, min(rt_storm_n, 50_000)),
        runtime_retry_storm_window_sec=max(5.0, min(rt_storm_w, 3600.0)),
        runtime_active_job_warn_sec=max(5.0, min(rt_active, 86400.0)),
        runtime_queue_growth_warn_depth=max(50, min(rt_growth, 10_000_000)),
        worker_retry_safe=worker_retry_safe,
        publish_lock_strict=publish_lock_strict,
        runtime_drift_monitor_enabled=runtime_drift_monitor_enabled,
        scheduler_diagnostics_enabled=scheduler_diagnostics_enabled,
        security_redaction_enabled=security_redaction_enabled,
    )
