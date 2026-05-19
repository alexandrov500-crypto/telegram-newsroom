from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from prometheus_client import Counter, Gauge, Histogram

# Ingestion
ARTICLES_INGESTED = Counter(
    "articles_ingested_total",
    "Articles enqueued for editorial review",
    ["source"],
)
RSS_FETCH_FAILURES = Counter(
    "rss_fetch_failures_total",
    "RSS feed fetch failures",
    ["feed"],
)
SOURCE_FETCH_LATENCY = Histogram(
    "source_fetch_latency_seconds",
    "Latency fetching a source feed",
    ["source_type"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 60.0),
)

# AI pipeline
OPENAI_REQUESTS = Counter(
    "openai_requests_total",
    "OpenAI API requests",
    ["operation", "model", "status"],
)
OPENAI_TOKENS = Counter(
    "openai_tokens_total",
    "OpenAI token usage",
    ["operation", "model", "token_type"],
)
OPENAI_COST_USD = Counter(
    "openai_cost_usd_total",
    "Estimated OpenAI spend in USD",
    ["operation", "model"],
)
SUMMARIZATION_FAILURES = Counter(
    "summarization_failures_total",
    "Summarization failures",
)
TRANSLATION_FAILURES = Counter(
    "translation_failures_total",
    "Translation/localization failures",
)

# Clustering
DUPLICATE_ARTICLES = Counter(
    "duplicate_articles_total",
    "Duplicate or skipped articles",
    ["reason"],
)
CLUSTERS_CREATED = Counter(
    "clusters_created_total",
    "New story clusters created",
)

# Publishing
TELEGRAM_PUBLISH_SUCCESS = Counter(
    "telegram_publish_success_total",
    "Successful Telegram publishes",
    ["language"],
)
TELEGRAM_PUBLISH_FAILURES = Counter(
    "telegram_publish_failures_total",
    "Failed Telegram publishes",
    ["language", "reason"],
)
PUBLISH_LATENCY = Histogram(
    "publish_latency_seconds",
    "Telegram publish latency",
    ["language"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)

# System
ACTIVE_JOBS = Gauge("active_jobs", "Active asyncio background jobs")
QUEUE_BACKLOG = Gauge("queue_backlog", "Pending editorial queue depth")
PROCESS_MEMORY_MB = Gauge("process_memory_mb", "Process RSS memory megabytes")
EVENT_LOOP_LATENCY = Histogram(
    "event_loop_latency_seconds",
    "Event loop scheduling lag probe",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0),
)

# Editorial story memory
STORIES_ACTIVE = Gauge("stories_active_total", "Active editorial stories in registry")
STORY_UPDATES = Counter(
    "story_updates_total",
    "Story create/update operations",
    ["kind"],
)
STORY_ESCALATIONS = Counter(
    "story_escalations_total",
    "Story escalation or milestone events",
)
DIGEST_STORY_COUNT = Gauge(
    "digest_story_count",
    "Stories included in last narrative digest build",
)
NARRATIVE_DETECTION_LATENCY = Histogram(
    "narrative_detection_latency_seconds",
    "Story match and persistence latency",
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0),
)
IMPORTANCE_SCORE = Histogram(
    "importance_score_distribution",
    "Editorial importance scores for story updates",
    buckets=(0.1, 0.25, 0.5, 0.65, 0.75, 0.85, 0.9, 0.95, 1.0),
)

# Signal intelligence
SIGNALS_DETECTED = Counter(
    "signals_detected_total",
    "Editorial signals detected per ingest batch",
)
SIGNAL_DETECTION_LATENCY = Histogram(
    "signal_detection_latency_seconds",
    "End-to-end signal intelligence latency",
    buckets=(0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
ANOMALIES_DETECTED = Counter(
    "anomalies_detected_total",
    "Anomalies flagged by anomaly engine",
    ["anomaly_type"],
)
EVENT_BUS_DROPPED = Counter(
    "event_bus_dropped_total",
    "Events dropped due to backpressure",
)
FORECAST_ESCALATIONS = Counter(
    "forecast_escalations_total",
    "High-probability trend escalation forecasts",
)

# Adaptive operations
ADAPTIVE_POLICY_CHANGES = Counter(
    "adaptive_policy_changes_total",
    "Operator or self-tuning policy updates",
)
FORECAST_ACCURACY = Gauge("forecast_accuracy_score", "Rolling forecast reliability")
SIGNAL_PRECISION = Gauge("signal_precision_score", "Rolling signal precision")
AGENT_DECISIONS = Counter(
    "agent_decisions_total",
    "Autonomous editorial decisions audited",
    ["action"],
)
REPLAY_RUNS = Counter("replay_runs_total", "Replay engine executions")
COST_OPTIMIZATION_SAVINGS = Counter(
    "cost_optimization_savings_total",
    "Estimated USD saved by cost optimizer skips",
)


def record_article_ingested(source: str = "unknown") -> None:
    ARTICLES_INGESTED.labels(source=source).inc()


def record_rss_fetch_failure(feed: str) -> None:
    RSS_FETCH_FAILURES.labels(feed=feed).inc()


def record_openai_usage(
    *,
    operation: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    success: bool,
    cost_usd: float = 0.0,
) -> None:
    status = "success" if success else "error"
    OPENAI_REQUESTS.labels(operation=operation, model=model, status=status).inc()
    if prompt_tokens:
        OPENAI_TOKENS.labels(
            operation=operation,
            model=model,
            token_type="prompt",
        ).inc(prompt_tokens)
    if completion_tokens:
        OPENAI_TOKENS.labels(
            operation=operation,
            model=model,
            token_type="completion",
        ).inc(completion_tokens)
    if cost_usd > 0:
        OPENAI_COST_USD.labels(operation=operation, model=model).inc(cost_usd)


def record_summarization_failure() -> None:
    SUMMARIZATION_FAILURES.inc()


def record_translation_failure() -> None:
    TRANSLATION_FAILURES.inc()


def record_duplicate(reason: str) -> None:
    DUPLICATE_ARTICLES.labels(reason=reason).inc()


def record_cluster_created() -> None:
    CLUSTERS_CREATED.inc()


def record_publish_success(language: str, duration_sec: float) -> None:
    TELEGRAM_PUBLISH_SUCCESS.labels(language=language).inc()
    PUBLISH_LATENCY.labels(language=language).observe(duration_sec)


def record_publish_failure(language: str, reason: str) -> None:
    TELEGRAM_PUBLISH_FAILURES.labels(language=language, reason=reason).inc()


def set_queue_backlog(count: int) -> None:
    QUEUE_BACKLOG.set(max(0, count))


def set_active_jobs(count: int) -> None:
    ACTIVE_JOBS.set(max(0, count))


def set_process_memory_mb(value: float) -> None:
    PROCESS_MEMORY_MB.set(max(0.0, value))


EVENT_LOOP_LAG_AVG = Gauge(
    "event_loop_lag_avg_seconds",
    "Rolling average event loop scheduling lag",
)
EVENT_LOOP_LAG_MAX = Gauge(
    "event_loop_lag_max_seconds",
    "Peak event loop scheduling lag since process start",
)
SLOW_JOB_COUNT = Counter(
    "slow_job_total",
    "Background jobs exceeding warn threshold",
    ["job_name"],
)
SLOW_DB_OPERATION_COUNT = Counter(
    "slow_db_operation_total",
    "Sync DB operations exceeding warn threshold",
    ["operation"],
)


def observe_event_loop_lag(seconds: float) -> None:
    EVENT_LOOP_LATENCY.observe(max(0.0, seconds))


def set_event_loop_lag_stats(avg_sec: float, max_sec: float) -> None:
    EVENT_LOOP_LAG_AVG.set(max(0.0, avg_sec))
    EVENT_LOOP_LAG_MAX.set(max(0.0, max_sec))


def record_slow_job(job_name: str, duration_sec: float) -> None:
    SLOW_JOB_COUNT.labels(job_name=job_name[:48]).inc()


def record_slow_db_operation(operation: str, duration_sec: float) -> None:
    SLOW_DB_OPERATION_COUNT.labels(operation=operation[:48]).inc()


RSS_LOOP_DURATION_AVG = Gauge(
    "rss_loop_duration_avg_seconds",
    "RSS ingestion loop average iteration duration",
)
RSS_LOOP_DURATION_MAX = Gauge(
    "rss_loop_duration_max_seconds",
    "RSS ingestion loop peak iteration duration",
)
AUTONOMOUS_LOOP_DURATION_AVG = Gauge(
    "autonomous_loop_duration_avg_seconds",
    "Autonomous runtime loop average tick duration",
)
AUTONOMOUS_LOOP_DURATION_MAX = Gauge(
    "autonomous_loop_duration_max_seconds",
    "Autonomous runtime loop peak tick duration",
)
AUTONOMOUS_PASSIVE_MODE = Gauge(
    "autonomous_passive_mode",
    "1 when autonomous loop is passive (pilot canary)",
)
STALLED_LOOP_COUNT = Gauge("stalled_loop_count", "Background loops currently stalled")
RUNTIME_RECOVERY_RATE = Gauge(
    "runtime_recovery_rate",
    "Fraction of recovery attempts allowed vs suppressed",
)


def set_rss_loop_health(*, avg: float, max_sec: float) -> None:
    RSS_LOOP_DURATION_AVG.set(max(0.0, avg))
    RSS_LOOP_DURATION_MAX.set(max(0.0, max_sec))


def set_autonomous_loop_health(*, avg: float, max_sec: float, passive: bool) -> None:
    AUTONOMOUS_LOOP_DURATION_AVG.set(max(0.0, avg))
    AUTONOMOUS_LOOP_DURATION_MAX.set(max(0.0, max_sec))
    AUTONOMOUS_PASSIVE_MODE.set(1.0 if passive else 0.0)


def set_stalled_loop_count_metric(count: int) -> None:
    STALLED_LOOP_COUNT.set(max(0, count))


def set_runtime_recovery_rate(rate: float) -> None:
    RUNTIME_RECOVERY_RATE.set(max(0.0, min(1.0, rate)))


@contextmanager
def observe_publish_latency(language: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        PUBLISH_LATENCY.labels(language=language).observe(time.perf_counter() - started)


@contextmanager
def observe_source_fetch(source_type: str) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        SOURCE_FETCH_LATENCY.labels(source_type=source_type).observe(
            time.perf_counter() - started
        )


def refresh_story_gauges(active_count: int) -> None:
    STORIES_ACTIVE.set(max(0, active_count))


def record_story_update(*, created: bool) -> None:
    STORY_UPDATES.labels(kind="created" if created else "updated").inc()


def record_story_escalation() -> None:
    STORY_ESCALATIONS.inc()


def set_digest_story_count(count: int) -> None:
    DIGEST_STORY_COUNT.set(max(0, count))


def observe_narrative_detection(seconds: float) -> None:
    NARRATIVE_DETECTION_LATENCY.observe(max(0.0, seconds))


def observe_importance_score(score: float) -> None:
    IMPORTANCE_SCORE.observe(max(0.0, min(1.0, score)))


def record_signal_detected(count: int = 1) -> None:
    if count > 0:
        SIGNALS_DETECTED.inc(count)


def observe_signal_detection(seconds: float) -> None:
    SIGNAL_DETECTION_LATENCY.observe(max(0.0, seconds))


def record_anomaly_detected(anomaly_type: str) -> None:
    ANOMALIES_DETECTED.labels(anomaly_type=anomaly_type).inc()


def record_event_bus_dropped() -> None:
    EVENT_BUS_DROPPED.inc()


def record_forecast_escalation() -> None:
    FORECAST_ESCALATIONS.inc()


def record_policy_change() -> None:
    ADAPTIVE_POLICY_CHANGES.inc()


def set_forecast_accuracy(score: float) -> None:
    FORECAST_ACCURACY.set(max(0.0, min(1.0, score)))


def set_signal_precision(score: float) -> None:
    SIGNAL_PRECISION.set(max(0.0, min(1.0, score)))


def record_agent_decision(action: str) -> None:
    AGENT_DECISIONS.labels(action=action[:32]).inc()


def record_replay_run() -> None:
    REPLAY_RUNS.inc()


def record_cost_savings_usd(amount: float) -> None:
    if amount > 0:
        COST_OPTIMIZATION_SAVINGS.inc(amount)


# Distributed cluster
CLUSTER_NODES = Gauge("cluster_nodes_total", "Healthy cluster nodes", ["status"])
CLUSTER_LEADER_CHANGES = Counter(
    "cluster_leader_changes_total",
    "Cluster leader election changes",
)
DISTRIBUTED_EVENTS = Counter(
    "distributed_events_total",
    "Events published on distributed bus",
    ["backend", "event_type"],
)
EVENT_LAG_SECONDS = Gauge("event_lag_seconds", "Event processing lag", ["topic"])
WORKER_ASSIGNMENTS = Gauge(
    "worker_assignment_count",
    "Partition assignments per node",
    ["node_id"],
)
PARTITION_LATENCY = Histogram(
    "partition_processing_latency_seconds",
    "Partition ingest/processing latency",
    ["partition"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
)
NODE_FAILOVERS = Counter("node_failovers_total", "Node failover events")


def set_cluster_nodes(*, healthy: int, draining: int, offline: int) -> None:
    CLUSTER_NODES.labels(status="healthy").set(healthy)
    CLUSTER_NODES.labels(status="draining").set(draining)
    CLUSTER_NODES.labels(status="offline").set(offline)


def record_cluster_leader_change() -> None:
    CLUSTER_LEADER_CHANGES.inc()


def record_distributed_event(*, backend: str, event_type: str) -> None:
    DISTRIBUTED_EVENTS.labels(backend=backend, event_type=event_type).inc()


def set_event_lag(topic: str, seconds: float) -> None:
    EVENT_LAG_SECONDS.labels(topic=topic).set(max(0.0, seconds))


def set_worker_assignments(node_id: str, count: int) -> None:
    WORKER_ASSIGNMENTS.labels(node_id=node_id).set(max(0, count))


def observe_partition_latency(partition: str, seconds: float) -> None:
    PARTITION_LATENCY.labels(partition=partition).observe(max(0.0, seconds))


def record_node_failover() -> None:
    NODE_FAILOVERS.inc()


# Event-sourced pipeline
STREAM_PUBLISH_TOTAL = Counter(
    "stream_publish_total",
    "Events appended to durable streams",
    ["partition"],
)
STREAM_DLQ_TOTAL = Counter(
    "stream_dlq_total",
    "Stream dead-letter / quarantine events",
    ["event_type"],
)
STREAM_PENDING = Gauge("stream_pending_messages", "Unacked stream messages")
STREAM_REPLAY_TOTAL = Counter("stream_replay_total", "Stream replay operations")
SOURCED_EVENTS_TOTAL = Counter(
    "sourced_events_total",
    "Append-only sourced events",
    ["event_type", "status"],
)
WORKFLOW_RECOVERY_TOTAL = Counter(
    "workflow_recovery_total",
    "Workflow recovery takeovers",
    ["workflow_type"],
)
WORKFLOW_STALLED = Gauge("workflow_stalled_total", "Stalled workflow runs")
PUBLISH_DEDUP_TOTAL = Counter(
    "publish_dedup_suppressed_total",
    "Duplicate publishes suppressed",
    ["reason"],
)
TRACE_SPANS_TOTAL = Counter(
    "trace_spans_total",
    "Tracing spans created",
    ["operation"],
)


def record_stream_publish(partition: str) -> None:
    STREAM_PUBLISH_TOTAL.labels(partition=partition[:32]).inc()


def record_stream_quarantine(event_type: str) -> None:
    STREAM_DLQ_TOTAL.labels(event_type=event_type[:32]).inc()


def set_stream_pending(count: int) -> None:
    STREAM_PENDING.set(max(0, count))


def record_stream_replay(count: int = 1) -> None:
    if count > 0:
        STREAM_REPLAY_TOTAL.inc(count)


def record_sourced_event(*, event_type: str, status: str = "pending") -> None:
    SOURCED_EVENTS_TOTAL.labels(event_type=event_type[:32], status=status).inc()


def record_workflow_recovery(workflow_type: str) -> None:
    WORKFLOW_RECOVERY_TOTAL.labels(workflow_type=workflow_type[:32]).inc()


def set_workflow_stalled(count: int) -> None:
    WORKFLOW_STALLED.set(max(0, count))


def record_publish_dedup(reason: str = "duplicate") -> None:
    PUBLISH_DEDUP_TOTAL.labels(reason=reason[:32]).inc()


def record_trace_span(operation: str) -> None:
    TRACE_SPANS_TOTAL.labels(operation=operation[:32]).inc()


TOPOLOGY_HEALTH = Gauge("topology_health_score", "Cluster topology health 0-1")
DEGRADATION_MODE = Gauge(
    "degradation_mode_active",
    "Active degradation mode (labeled by mode name)",
    ["mode"],
)
POLICY_DECISIONS = Counter(
    "policy_decisions_total",
    "Policy evaluations",
    ["kind", "action"],
)
AUTONOMOUS_ACTIONS = Counter(
    "autonomous_operations_total",
    "Autonomous operational actions",
    ["action"],
)
SCHEDULER_PRESSURE = Gauge("scheduler_pressure_score", "Adaptive scheduler load pressure")


def set_topology_health(score: float) -> None:
    TOPOLOGY_HEALTH.set(max(0.0, min(1.0, score)))


def set_degradation_mode(mode: str) -> None:
    for label in (
        "normal",
        "read_only",
        "publish_safe",
        "degraded_federation",
        "low_memory",
        "replay_only",
        "operator_only",
    ):
        DEGRADATION_MODE.labels(mode=label).set(1.0 if label == mode else 0.0)


def record_degradation_transition(mode: str) -> None:
    set_degradation_mode(mode)


def record_policy_decision(*, kind: str, action: str) -> None:
    POLICY_DECISIONS.labels(kind=kind[:24], action=action[:24]).inc()


def record_autonomous_action(action: str) -> None:
    AUTONOMOUS_ACTIONS.labels(action=action[:32]).inc()


def set_scheduler_pressure(score: float) -> None:
    SCHEDULER_PRESSURE.set(max(0.0, min(1.0, score)))


COGNITIVE_HEALTH = Gauge("cognitive_health_score", "Editorial cognitive runtime health 0-1")
EVALUATION_SCORES = Histogram(
    "cognitive_evaluation_score",
    "Evaluation scores by evaluator",
    ["evaluator"],
    buckets=(0.1, 0.25, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
MODEL_ROUTES = Counter(
    "cognitive_model_routes_total",
    "Adaptive model routing decisions",
    ["model", "strategy"],
)
COGNITIVE_SPEND = Counter("cognitive_spend_usd_total", "Cognitive runtime estimated spend USD")
PREDICTIONS_TOTAL = Counter(
    "cognitive_predictions_total",
    "Operational predictions emitted",
    ["forecast_type"],
)
SIMULATION_RUNS = Counter(
    "cognitive_simulation_runs_total",
    "Simulation runs",
    ["scenario", "status"],
)


def set_cognitive_health(score: float) -> None:
    COGNITIVE_HEALTH.set(max(0.0, min(1.0, score)))


def record_evaluation_score(evaluator: str, score: float) -> None:
    EVALUATION_SCORES.labels(evaluator=evaluator[:32]).observe(max(0.0, min(1.0, score)))


def record_model_route(model: str, strategy: str) -> None:
    MODEL_ROUTES.labels(model=model[:32], strategy=strategy[:32]).inc()


def record_cognitive_spend(usd: float) -> None:
    if usd > 0:
        COGNITIVE_SPEND.inc(usd)


def record_prediction(forecast_type: str) -> None:
    PREDICTIONS_TOTAL.labels(forecast_type=forecast_type[:32]).inc()


def record_simulation_run(scenario: str, *, passed: bool) -> None:
    SIMULATION_RUNS.labels(scenario=scenario[:32], status="passed" if passed else "failed").inc()


MESH_HEALTH = Gauge("mesh_health_score", "Federated cognitive mesh health 0-1")
MESH_COGNITIVE_EVENTS = Counter(
    "mesh_cognitive_events_total",
    "Cognitive mesh events propagated",
    ["lane", "event_type"],
)
MESH_CONSENSUS = Counter(
    "mesh_consensus_sessions_total",
    "Collaborative reasoning sessions completed",
    ["status"],
)
MESH_TOURNAMENTS = Counter(
    "mesh_simulation_tournaments_total",
    "Federated simulation tournaments",
    ["status"],
)
MESH_GOSSIP_BUDGET = Gauge("mesh_gossip_budget_remaining", "Remaining gossip budget per tick")


def set_mesh_health(score: float) -> None:
    MESH_HEALTH.set(max(0.0, min(1.0, score)))


def record_mesh_cognitive_event(lane: str, event_type: str) -> None:
    MESH_COGNITIVE_EVENTS.labels(lane=lane[:16], event_type=event_type[:32]).inc()


def record_mesh_consensus(*, completed: bool) -> None:
    MESH_CONSENSUS.labels(status="completed" if completed else "failed").inc()


def record_mesh_tournament(passed: bool) -> None:
    MESH_TOURNAMENTS.labels(status="passed" if passed else "failed").inc()


def set_mesh_gossip_budget(remaining: int) -> None:
    MESH_GOSSIP_BUDGET.set(max(0, remaining))


EPISTEMIC_STABILITY = Gauge("epistemic_stability_score", "Epistemic federation stability 0-1")
MISINFO_PRESSURE = Gauge("misinformation_pressure_score", "Pending misinformation alert pressure")
EPISTEMIC_CONTRADICTIONS = Gauge("epistemic_open_contradictions", "Open contradiction count")
EPISTEMIC_ALERTS = Counter(
    "epistemic_alerts_total",
    "Epistemic integrity alerts",
    ["alert_type"],
)
EPISTEMIC_REPLAY = Counter(
    "epistemic_replay_runs_total",
    "Epistemic replay validation runs",
    ["status"],
)


def set_epistemic_stability(score: float) -> None:
    EPISTEMIC_STABILITY.set(max(0.0, min(1.0, score)))


def set_misinformation_pressure(score: float) -> None:
    MISINFO_PRESSURE.set(max(0.0, min(1.0, score)))


def set_open_contradictions(count: int) -> None:
    EPISTEMIC_CONTRADICTIONS.set(max(0, count))


def record_epistemic_alert(alert_type: str, severity: float) -> None:
    EPISTEMIC_ALERTS.labels(alert_type=alert_type[:32]).inc()


def record_epistemic_replay(passed: bool) -> None:
    EPISTEMIC_REPLAY.labels(status="passed" if passed else "failed").inc()


BURNIN_HEALTH = Gauge("burnin_health_score", "Long-run burn-in health 0-1")
FEED_RELIABILITY = Gauge(
    "feed_reliability_score",
    "RSS feed reliability score",
    ["source"],
)
FEED_MALFORMED = Counter(
    "feed_malformed_total",
    "Malformed feed entries",
    ["source"],
)
OPS_COST = Counter(
    "ops_cost_usd_total",
    "Operations platform cost attribution USD",
    ["region"],
)
CERTIFICATION_PASSED = Gauge("certification_passed", "1 if latest certification passed else 0")


def set_burnin_health(score: float) -> None:
    BURNIN_HEALTH.set(max(0.0, min(1.0, score)))


def record_feed_validation(source: str, reliability: float, malformed: int) -> None:
    FEED_RELIABILITY.labels(source=source[:32]).set(max(0.0, min(1.0, reliability)))
    if malformed > 0:
        FEED_MALFORMED.labels(source=source[:32]).inc(malformed)


def record_ops_cost(usd: float, region: str) -> None:
    if usd > 0:
        OPS_COST.labels(region=region[:16]).inc(usd)


def set_certification_status(passed: bool) -> None:
    CERTIFICATION_PASSED.set(1.0 if passed else 0.0)


STAGING_SHADOW_PUBLISHES = Counter(
    "staging_shadow_publish_total",
    "Shadow staging channel publishes",
)
REPLAY_LAG_SECONDS = Gauge("replay_lag_seconds", "Estimated replay reconstruction lag")
STREAM_BACKLOG = Gauge("stream_backlog_events", "Redis stream pending events")
GOSSIP_PRESSURE = Gauge("gossip_pressure_ratio", "Federation gossip pressure 0-1")
SCHEDULER_PRESSURE = Gauge("scheduler_pressure_ratio", "Scheduler load pressure 0-1")
CONFIDENCE_VARIANCE = Gauge("confidence_variance", "Epistemic confidence variance")
EVENT_AMPLIFICATION = Gauge("event_amplification_ratio", "Mesh/sourced event amplification")
LONG_RUN_HEALTH = Gauge("long_run_health_score", "Continuous staging health 0-1")
RUNTIME_HEALTH_SCORE = Gauge(
    "runtime_health_score",
    "Unified runtime health score 0-1 (reliability layer)",
)
RELIABILITY_DEGRADED = Gauge(
    "reliability_degraded_mode",
    "1 when runtime is in degraded or worse state",
)
RELIABILITY_INCIDENTS_OPEN = Gauge(
    "reliability_open_incidents",
    "Open production incidents",
)
INGESTION_PRESSURE = Counter(
    "ingestion_pressure_total",
    "Feed ingestion pressure signals",
    ["source"],
)


def record_staging_shadow_publish() -> None:
    STAGING_SHADOW_PUBLISHES.inc()


def set_replay_lag(seconds: float) -> None:
    REPLAY_LAG_SECONDS.set(max(0.0, seconds))


def set_stream_backlog(count: int) -> None:
    STREAM_BACKLOG.set(max(0, count))


def set_gossip_pressure(ratio: float) -> None:
    GOSSIP_PRESSURE.set(max(0.0, min(1.0, ratio)))


def set_scheduler_pressure(ratio: float) -> None:
    SCHEDULER_PRESSURE.set(max(0.0, min(1.0, ratio)))


def set_confidence_variance(value: float) -> None:
    CONFIDENCE_VARIANCE.set(max(0.0, value))


def set_event_amplification(ratio: float) -> None:
    EVENT_AMPLIFICATION.set(max(0.0, ratio))


def set_long_run_health(score: float) -> None:
    LONG_RUN_HEALTH.set(max(0.0, min(1.0, score)))


def set_runtime_health_score(score: float) -> None:
    RUNTIME_HEALTH_SCORE.set(max(0.0, min(1.0, score)))


def set_reliability_degraded(degraded: bool) -> None:
    RELIABILITY_DEGRADED.set(1.0 if degraded else 0.0)


def set_reliability_open_incidents(count: int) -> None:
    RELIABILITY_INCIDENTS_OPEN.set(max(0, count))


def record_ingestion_pressure(source: str) -> None:
    INGESTION_PRESSURE.labels(source=source[:32]).inc()


STARTUP_VALIDATION_PASSED = Gauge(
    "startup_validation_passed",
    "1 if latest startup validation passed else 0",
)
STARTUP_CHECK_FAILURES = Counter(
    "startup_check_failures_total",
    "Startup validation check failures",
    ["check_id"],
)


OPERATOR_TELEGRAM_MESSAGES = Counter(
    "operator_telegram_messages_total",
    "Operator console Telegram notifications",
    ["category"],
)
OPERATOR_CONSOLE_AGGREGATED = Counter(
    "operator_console_aggregated_messages_total",
    "Operator console messages delivered via aggregation",
    ["kind"],
)
OPERATOR_CONSOLE_SUPPRESSED = Counter(
    "operator_console_suppressed_messages_total",
    "Operator console messages suppressed by fatigue routing",
    ["severity"],
)
OPERATOR_CONSOLE_BURST_COLLAPSES = Counter(
    "operator_console_burst_collapses_total",
    "Approval/signal burst collapses into batch digests",
)
OPERATOR_FATIGUE_SCORE = Gauge(
    "operator_fatigue_score",
    "Current operator console fatigue score (0-1)",
)


def record_operator_telegram_message(category: str) -> None:
    OPERATOR_TELEGRAM_MESSAGES.labels(category=category[:32]).inc()


def record_operator_aggregated(kind: str) -> None:
    OPERATOR_CONSOLE_AGGREGATED.labels(kind=kind[:32]).inc()


def record_operator_suppressed(severity: str) -> None:
    OPERATOR_CONSOLE_SUPPRESSED.labels(severity=severity[:16]).inc()


def record_operator_burst_collapse() -> None:
    OPERATOR_CONSOLE_BURST_COLLAPSES.inc()


def set_operator_fatigue_score(score: float) -> None:
    OPERATOR_FATIGUE_SCORE.set(max(0.0, min(1.0, score)))


RUNTIME_LOOP_LATENCY = Histogram(
    "runtime_loop_latency_seconds",
    "Background loop tick duration",
    ["loop"],
    buckets=(0.05, 0.1, 0.5, 1.0, 5.0, 15.0, 60.0, 180.0, 300.0),
)
RUNTIME_WATCHDOG_RESTARTS = Counter(
    "runtime_watchdog_restarts_total",
    "Runtime supervisor recovery actions",
)
STALLED_TASK_COUNT = Gauge("stalled_task_count", "Stalled loops/tasks detected")
TELEGRAM_DELIVERY_FAILURES = Counter(
    "telegram_delivery_failures_total",
    "Failed Telegram outbound deliveries",
)
TELEGRAM_DELIVERY_LATENCY = Histogram(
    "telegram_delivery_latency_seconds",
    "Telegram outbound delivery latency",
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 15.0, 30.0),
)
TELEGRAM_DUPLICATE_SEND_PREVENTED = Counter(
    "telegram_duplicate_send_prevented_total",
    "Duplicate Telegram sends prevented",
)
MALFORMED_FEED_EVENTS = Counter("malformed_feed_events_total", "Malformed RSS feed items")
FEED_QUARANTINE = Counter("feed_quarantine_total", "Feeds quarantined")
DUPLICATE_BURST_SUPPRESSED = Counter("duplicate_burst_suppressed_total", "Ingest duplicate bursts suppressed")
REPLAY_SUSTAINABILITY_SCORE = Gauge("replay_sustainability_score", "Replay sustainability 0-1")
OPERATIONAL_READINESS_SCORE = Gauge(
    "operational_readiness_score",
    "Composite operational readiness 0-1",
)


def observe_runtime_loop_latency(loop: str, seconds: float) -> None:
    RUNTIME_LOOP_LATENCY.labels(loop=loop[:32]).observe(max(0.0, seconds))


def record_runtime_watchdog_restart() -> None:
    RUNTIME_WATCHDOG_RESTARTS.inc()


def set_stalled_task_count(count: int) -> None:
    STALLED_TASK_COUNT.set(max(0, count))


TELEGRAM_FLOODWAIT_TOTAL = Counter(
    "telegram_floodwait_total",
    "Telegram FloodWait events",
)


def record_telegram_floodwait() -> None:
    TELEGRAM_FLOODWAIT_TOTAL.inc()


def record_telegram_delivery_failure() -> None:
    TELEGRAM_DELIVERY_FAILURES.inc()


def observe_telegram_delivery_latency(seconds: float) -> None:
    TELEGRAM_DELIVERY_LATENCY.observe(max(0.0, seconds))


def record_telegram_duplicate_prevented() -> None:
    TELEGRAM_DUPLICATE_SEND_PREVENTED.inc()


def record_malformed_feed_event() -> None:
    MALFORMED_FEED_EVENTS.inc()


def record_feed_quarantine() -> None:
    FEED_QUARANTINE.inc()


def record_duplicate_burst_suppressed() -> None:
    DUPLICATE_BURST_SUPPRESSED.inc()


def set_replay_sustainability_score(score: float) -> None:
    REPLAY_SUSTAINABILITY_SCORE.set(max(0.0, min(1.0, score)))


def set_operational_readiness_score(score: float) -> None:
    OPERATIONAL_READINESS_SCORE.set(max(0.0, min(1.0, score)))


def record_startup_validation(passed: bool, checks: tuple) -> None:
    STARTUP_VALIDATION_PASSED.set(1.0 if passed else 0.0)
    for check in checks:
        if not check.passed:
            STARTUP_CHECK_FAILURES.labels(check_id=check.check_id[:48]).inc()


# Live operations
LIVE_OPS_EVENTS = Counter(
    "live_ops_events_total",
    "Live ops typed event bus emissions",
    ["event_type", "outcome"],
)
COGNITION_DURATION = Histogram(
    "live_ops_cognition_duration_seconds",
    "Cognition pipeline duration",
    buckets=(0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)
LIVE_PUBLISH_LATENCY = Histogram(
    "live_ops_publish_latency_seconds",
    "End-to-end publish latency by channel",
    ["channel_id"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 15.0, 30.0, 60.0),
)
ROLLOUT_TRANSITIONS = Counter(
    "live_ops_rollout_transitions_total",
    "Rollout stage transitions",
    ["from_stage", "to_stage"],
)
OPERATOR_ACTIONS = Counter(
    "live_ops_operator_actions_total",
    "Operator command center actions",
    ["command"],
)
LONG_RUN_STABILITY = Gauge(
    "live_ops_stability_score",
    "Rolling multi-day stability score (0-1)",
)
STORY_LIFECYCLE_EVENTS = Counter(
    "live_ops_story_lifecycle_total",
    "Story lifecycle stage transitions",
    ["stage"],
)
QUEUE_LATENCY = Histogram(
    "live_ops_queue_latency_seconds",
    "Queue wait latency",
    ["queue"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 15.0, 60.0),
)


def record_live_ops_event(event_type: str, outcome: str) -> None:
    LIVE_OPS_EVENTS.labels(event_type=event_type[:48], outcome=outcome[:24]).inc()


def observe_cognition_duration(seconds: float) -> None:
    COGNITION_DURATION.observe(max(0.0, seconds))


def observe_live_publish_latency(channel_id: str, seconds: float) -> None:
    LIVE_PUBLISH_LATENCY.labels(channel_id=channel_id[:32]).observe(max(0.0, seconds))


def record_rollout_transition(from_stage: str, to_stage: str) -> None:
    ROLLOUT_TRANSITIONS.labels(
        from_stage=from_stage[:32],
        to_stage=to_stage[:32],
    ).inc()


def record_operator_action(command: str) -> None:
    OPERATOR_ACTIONS.labels(command=command[:48]).inc()


def set_long_run_stability_score(score: float) -> None:
    LONG_RUN_STABILITY.set(max(0.0, min(1.0, score)))


def record_story_lifecycle(stage: str) -> None:
    STORY_LIFECYCLE_EVENTS.labels(stage=stage[:32]).inc()


def observe_queue_latency(queue: str, seconds: float) -> None:
    QUEUE_LATENCY.labels(queue=queue[:32]).observe(max(0.0, seconds))


# Ops certification
SLO_COMPLIANCE = Gauge(
    "ops_slo_compliance_ratio",
    "SLO compliance ratio",
    ["slo_name"],
)
SLO_BURN_RATE = Gauge(
    "ops_slo_burn_rate",
    "SLO error budget burn rate",
    ["slo_name"],
)
SLO_SAMPLES = Counter(
    "ops_slo_samples_total",
    "SLO sample recordings",
    ["slo_name", "success"],
)
CERTIFICATION_SCORE = Gauge("ops_certification_score", "Production certification score")
CERTIFICATION_STATE = Gauge(
    "ops_certification_state",
    "Certification state ordinal (0=NOT_READY .. 3=LOCKED)",
)
CHAOS_SURVIVABILITY = Gauge(
    "ops_chaos_survivability_score",
    "Last chaos drill survivability",
)
RUNTIME_AGING_SCORE = Gauge("ops_runtime_aging_score", "Month-long runtime aging score")
GOVERNANCE_FROZEN = Gauge("ops_governance_editorial_frozen", "Editorial freeze active")


def record_slo_sample(slo_name: str, success: bool) -> None:
    SLO_SAMPLES.labels(slo_name=slo_name[:32], success="true" if success else "false").inc()


def set_slo_gauges(slo_name: str, compliance: float, burn_rate: float) -> None:
    SLO_COMPLIANCE.labels(slo_name=slo_name[:32]).set(max(0.0, min(1.0, compliance)))
    SLO_BURN_RATE.labels(slo_name=slo_name[:32]).set(max(0.0, burn_rate))


def set_certification_metrics(score: float, state: str) -> None:
    CERTIFICATION_SCORE.set(max(0.0, min(1.0, score)))
    state_map = {"NOT_READY": 0, "CONDITIONAL": 1, "CERTIFIED": 2, "LOCKED_DOWN": 3}
    CERTIFICATION_STATE.set(float(state_map.get(state, 0)))


def set_chaos_survivability(score: float) -> None:
    CHAOS_SURVIVABILITY.set(max(0.0, min(1.0, score)))


def set_runtime_aging_score(score: float) -> None:
    RUNTIME_AGING_SCORE.set(max(0.0, min(1.0, score)))


def set_governance_frozen(frozen: bool) -> None:
    GOVERNANCE_FROZEN.set(1.0 if frozen else 0.0)
