from __future__ import annotations

import sqlite3
from pathlib import Path

from bot.config import project_root

_DB_FILENAME = "newsroom.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pending_news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    summary TEXT,
    link TEXT NOT NULL UNIQUE,
    tags TEXT,
    source TEXT,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,
    cluster_id INTEGER,
    priority_score REAL DEFAULT 0,
    priority_reason TEXT,
    source_count INTEGER DEFAULT 1,
    media_type TEXT DEFAULT 'none',
    media_url TEXT,
    thumbnail_url TEXT,
    media_width INTEGER,
    media_height INTEGER,
    optimized_headline TEXT,
    hook_line TEXT,
    caption_style TEXT DEFAULT 'optimized',
    source_language TEXT DEFAULT 'en',
    target_language TEXT,
    translated_title TEXT,
    translated_summary TEXT,
    localized_headline TEXT,
    localized_hook TEXT
);

CREATE TABLE IF NOT EXISTS news_localizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER NOT NULL,
    language TEXT NOT NULL,
    translated_title TEXT NOT NULL,
    translated_summary TEXT,
    localized_headline TEXT,
    localized_hook TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(pending_news_id, language)
);

CREATE TABLE IF NOT EXISTS story_clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_title TEXT NOT NULL,
    canonical_summary TEXT,
    embedding_hash TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_cluster_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id INTEGER NOT NULL,
    source TEXT,
    title TEXT,
    link TEXT UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    published_at TEXT,
    item_count INTEGER DEFAULT 0,
    language TEXT DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS digest_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    digest_id INTEGER NOT NULL,
    pending_news_id INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_seen_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    seen_at TEXT NOT NULL,
    UNIQUE(channel, message_id)
);

CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT UNIQUE NOT NULL,
    source_type TEXT NOT NULL,
    trust_score REAL DEFAULT 0.5,
    article_count INTEGER DEFAULT 0,
    accepted_count INTEGER DEFAULT 0,
    rejected_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    event_type TEXT NOT NULL,
    score_delta REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    mention_count INTEGER DEFAULT 0,
    canonical_key TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(entity_name, entity_type)
);

CREATE TABLE IF NOT EXISTS news_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER,
    cluster_id INTEGER,
    entity_id INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS published_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_message_id INTEGER,
    cluster_id INTEGER,
    pending_news_id INTEGER,
    published_at TEXT NOT NULL,
    headline TEXT,
    hook_line TEXT,
    entities_json TEXT,
    topics_json TEXT,
    priority_score REAL,
    source_trust REAL,
    language TEXT DEFAULT 'en'
);

CREATE TABLE IF NOT EXISTS post_analytics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    published_post_id INTEGER NOT NULL,
    views INTEGER DEFAULT 0,
    forwards INTEGER DEFAULT 0,
    reactions INTEGER DEFAULT 0,
    engagement_score REAL DEFAULT 0,
    collected_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS adaptive_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type TEXT NOT NULL,
    signal_key TEXT NOT NULL,
    sample_count INTEGER DEFAULT 0,
    avg_engagement REAL DEFAULT 0.5,
    updated_at TEXT NOT NULL,
    UNIQUE(signal_type, signal_key)
);

CREATE TABLE IF NOT EXISTS editorial_risk_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER NOT NULL,
    risk_score REAL NOT NULL,
    confidence_score REAL NOT NULL,
    factors_json TEXT,
    blocked_categories_json TEXT,
    requires_human_review INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editorial_agent_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER NOT NULL,
    action_type TEXT NOT NULL,
    decision_json TEXT,
    reversible INTEGER DEFAULT 0,
    reversed_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS openai_usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    success INTEGER DEFAULT 1,
    pending_news_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS openai_usage_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usage_date TEXT NOT NULL UNIQUE,
    request_count INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    cost_usd REAL DEFAULT 0,
    failure_count INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    canonical_summary TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    fingerprint_storage TEXT,
    geopolitical_tags TEXT,
    languages_json TEXT,
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    importance_score REAL DEFAULT 0.5,
    novelty_score REAL DEFAULT 0.5,
    trend_velocity REAL DEFAULT 0.0,
    cluster_count INTEGER DEFAULT 0,
    source_count INTEGER DEFAULT 0,
    canonical_cluster_id INTEGER
);

CREATE TABLE IF NOT EXISTS story_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    significance REAL NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    pending_news_id INTEGER,
    cluster_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_entities (
    story_id INTEGER NOT NULL,
    entity_name TEXT NOT NULL,
    entity_id INTEGER,
    mention_count INTEGER DEFAULT 1,
    PRIMARY KEY (story_id, entity_name)
);

CREATE TABLE IF NOT EXISTS story_metrics (
    story_id INTEGER PRIMARY KEY,
    importance_score REAL DEFAULT 0.5,
    novelty_score REAL DEFAULT 0.5,
    trend_velocity REAL DEFAULT 0.0,
    redundancy_score REAL DEFAULT 0.0,
    update_delta_score REAL DEFAULT 0.0,
    metrics_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    left_entity TEXT NOT NULL,
    right_entity TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    story_id INTEGER,
    updated_at TEXT NOT NULL,
    UNIQUE(left_entity, right_entity, story_id)
);

CREATE TABLE IF NOT EXISTS story_cluster_links (
    story_id INTEGER NOT NULL,
    cluster_id INTEGER NOT NULL UNIQUE,
    pending_news_id INTEGER,
    linked_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stories_status_updated
    ON stories(status, last_updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_events_story_created
    ON story_events(story_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_story_cluster_links_story
    ON story_cluster_links(story_id);

CREATE TABLE IF NOT EXISTS newsroom_event_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    velocity_score REAL DEFAULT 0,
    entities_json TEXT,
    story_id INTEGER,
    cluster_id INTEGER,
    pending_news_id INTEGER,
    source TEXT,
    title TEXT,
    summary TEXT,
    impact_json TEXT,
    forecast_json TEXT,
    priority_score REAL,
    editorial_action TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_anomalies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    anomaly_type TEXT NOT NULL,
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    severity REAL NOT NULL,
    baseline_value REAL,
    observed_value REAL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_baselines (
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    metric TEXT NOT NULL,
    mean_value REAL NOT NULL,
    std_value REAL NOT NULL,
    sample_count INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope, scope_key, metric)
);

CREATE TABLE IF NOT EXISTS signal_correlations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    narrative_key TEXT NOT NULL,
    origin_source TEXT,
    source_a TEXT NOT NULL,
    source_b TEXT NOT NULL,
    lag_seconds REAL,
    strength REAL NOT NULL,
    propagation_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER,
    signal_id INTEGER,
    forecast_probability REAL NOT NULL,
    expected_impact REAL NOT NULL,
    expected_reach REAL DEFAULT 0,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sentiment_windows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    sentiment_score REAL NOT NULL,
    velocity REAL DEFAULT 0,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_credibility_snapshots (
    source_name TEXT PRIMARY KEY,
    credibility_score REAL NOT NULL,
    risk_score REAL NOT NULL,
    bias_profile_json TEXT,
    sensationalism REAL DEFAULT 0,
    confirmation_latency REAL DEFAULT 0.5,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_type_created ON signals(signal_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_story ON signals(story_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_anomalies_created ON signal_anomalies(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_event_log_status ON newsroom_event_log(status, created_at);

CREATE TABLE IF NOT EXISTS editorial_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outcome_type TEXT NOT NULL,
    pending_news_id INTEGER,
    story_id INTEGER,
    signal_id INTEGER,
    source TEXT,
    label TEXT NOT NULL,
    score REAL NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_audits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    reason_json TEXT NOT NULL,
    scores_json TEXT NOT NULL,
    policy_name TEXT NOT NULL,
    pending_news_id INTEGER,
    story_id INTEGER,
    signal_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_key TEXT NOT NULL,
    metric_value REAL NOT NULL,
    window_hours INTEGER DEFAULT 168,
    detail_json TEXT,
    computed_at TEXT NOT NULL,
    UNIQUE(metric_key, window_hours)
);

CREATE TABLE IF NOT EXISTS agent_performance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    accuracy REAL DEFAULT 0.5,
    latency_ms REAL DEFAULT 0,
    usefulness REAL DEFAULT 0.5,
    false_positive_rate REAL DEFAULT 0,
    escalation_success REAL DEFAULT 0,
    publish_success REAL DEFAULT 0,
    snapshot_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS policy_state (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS adaptive_tuning (
    param_key TEXT PRIMARY KEY,
    current_value REAL NOT NULL,
    default_value REAL NOT NULL,
    min_value REAL NOT NULL,
    max_value REAL NOT NULL,
    last_adjusted_at TEXT NOT NULL,
    adjustment_log_json TEXT
);

CREATE TABLE IF NOT EXISTS source_dynamic_weights (
    source_name TEXT PRIMARY KEY,
    dynamic_weight REAL NOT NULL DEFAULT 1.0,
    base_trust REAL NOT NULL DEFAULT 0.5,
    false_escalation_rate REAL DEFAULT 0,
    adjustment_reason TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_key TEXT NOT NULL UNIQUE,
    memory_type TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    entities_json TEXT,
    relevance_score REAL DEFAULT 0.5,
    occurrence_count INTEGER DEFAULT 1,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replay_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_label TEXT NOT NULL,
    from_ts TEXT NOT NULL,
    to_ts TEXT NOT NULL,
    events_processed INTEGER DEFAULT 0,
    signals_matched INTEGER DEFAULT 0,
    policy_name TEXT,
    summary_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_outcomes_created ON editorial_outcomes(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audits_created ON decision_audits(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_relevance ON memory_index(relevance_score DESC);

CREATE TABLE IF NOT EXISTS cluster_nodes (
    node_id TEXT NOT NULL,
    role TEXT NOT NULL,
    region TEXT NOT NULL DEFAULT 'global',
    status TEXT NOT NULL DEFAULT 'starting',
    is_leader INTEGER NOT NULL DEFAULT 0,
    last_heartbeat_at TEXT NOT NULL,
    started_at TEXT NOT NULL,
    metadata_json TEXT,
    PRIMARY KEY (node_id, role)
);

CREATE TABLE IF NOT EXISTS cluster_leases (
    lease_name TEXT PRIMARY KEY,
    holder_node_id TEXT NOT NULL,
    holder_role TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    fencing_token INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cluster_job_leases (
    job_name TEXT PRIMARY KEY,
    holder_node_id TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cluster_partitions (
    partition_key TEXT PRIMARY KEY,
    assigned_node_id TEXT,
    paused INTEGER NOT NULL DEFAULT 0,
    lag_events INTEGER DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS story_federation (
    story_id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 1,
    origin_node_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    payload_hash TEXT
);

CREATE TABLE IF NOT EXISTS federated_learning_sync (
    sync_key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cluster_nodes_status ON cluster_nodes(status, last_heartbeat_at);

CREATE TABLE IF NOT EXISTS sourced_event_log (
    sequence_id INTEGER PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    envelope_json TEXT NOT NULL,
    partition_key TEXT NOT NULL DEFAULT 'global',
    correlation_id TEXT,
    causation_id TEXT,
    node_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    quarantine_reason TEXT,
    created_at TEXT NOT NULL,
    processed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sourced_event_correlation
    ON sourced_event_log(correlation_id, sequence_id);
CREATE INDEX IF NOT EXISTS idx_sourced_event_partition
    ON sourced_event_log(partition_key, sequence_id);
CREATE INDEX IF NOT EXISTS idx_sourced_event_status
    ON sourced_event_log(status, created_at);

CREATE TABLE IF NOT EXISTS publish_receipts (
    idempotency_key TEXT PRIMARY KEY,
    pending_news_id INTEGER,
    digest_id INTEGER,
    channel_id INTEGER,
    language TEXT,
    telegram_message_id INTEGER,
    node_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_publish_receipts_pending
    ON publish_receipts(pending_news_id);

CREATE TABLE IF NOT EXISTS workflow_runs (
    workflow_id TEXT PRIMARY KEY,
    workflow_type TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    holder_node_id TEXT NOT NULL,
    lease_expires_at TEXT,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS workflow_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    checkpoint_json TEXT NOT NULL,
    sequence_num INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(workflow_id, step_name)
);

CREATE INDEX IF NOT EXISTS idx_workflow_runs_status ON workflow_runs(status, updated_at);

CREATE TABLE IF NOT EXISTS cluster_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS policy_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    decision TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    node_id TEXT,
    context_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS degradation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL DEFAULT 'normal',
    previous_mode TEXT,
    reason TEXT,
    operator_override INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    updated_by TEXT
);

CREATE TABLE IF NOT EXISTS topology_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_json TEXT NOT NULL,
    health_score REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replay_checkpoints (
    checkpoint_key TEXT PRIMARY KEY,
    last_sequence_id INTEGER NOT NULL,
    lane TEXT NOT NULL DEFAULT 'default',
    rate_limit_per_sec REAL NOT NULL DEFAULT 50.0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS qos_sla_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_class TEXT NOT NULL,
    latency_ms REAL NOT NULL,
    success INTEGER NOT NULL DEFAULT 1,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_audit_created ON policy_audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_qos_sla_class ON qos_sla_samples(workflow_class, recorded_at DESC);

CREATE TABLE IF NOT EXISTS cognitive_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    evaluation_id TEXT PRIMARY KEY,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    evaluator_name TEXT NOT NULL,
    score REAL NOT NULL,
    dimensions_json TEXT NOT NULL,
    explanation TEXT,
    trace_id TEXT,
    replay_key TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluation_traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_id TEXT NOT NULL,
    step TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_route_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    route_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    model TEXT NOT NULL,
    strategy TEXT,
    qos_class TEXT,
    reason TEXT NOT NULL,
    context_json TEXT,
    node_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editorial_memory_entries (
    memory_id TEXT PRIMARY KEY,
    memory_type TEXT NOT NULL,
    subject_key TEXT NOT NULL,
    title TEXT,
    payload_json TEXT NOT NULL,
    temporal_bucket TEXT NOT NULL,
    region TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intelligence_graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    temporal_at TEXT NOT NULL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cognitive_agent_registry (
    agent_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    autonomy_bound INTEGER NOT NULL DEFAULT 1,
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    learning_kind TEXT NOT NULL,
    action TEXT NOT NULL,
    delta_json TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cost_budget_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    daily_spend_usd REAL NOT NULL DEFAULT 0,
    daily_budget_usd REAL NOT NULL DEFAULT 25.0,
    region_budgets_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS predictive_forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    forecast_type TEXT NOT NULL,
    horizon_minutes INTEGER NOT NULL,
    predicted_value REAL NOT NULL,
    confidence REAL NOT NULL,
    explanation TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS simulation_runs (
    run_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    lane TEXT NOT NULL DEFAULT 'shadow',
    status TEXT NOT NULL,
    scores_json TEXT,
    deterministic_seed INTEGER,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS operator_feedback_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    feedback_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    operator_id TEXT,
    annotation TEXT,
    rating REAL,
    payload_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cognitive_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    context_json TEXT,
    node_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evaluation_target ON evaluation_results(target_type, target_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_type_bucket ON editorial_memory_entries(memory_type, temporal_bucket);
CREATE INDEX IF NOT EXISTS idx_graph_from ON intelligence_graph_edges(from_node, edge_type);
CREATE INDEX IF NOT EXISTS idx_route_audit_created ON model_route_audit(created_at DESC);

CREATE TABLE IF NOT EXISTS mesh_cognitive_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    lane TEXT NOT NULL DEFAULT 'gossip',
    region TEXT NOT NULL,
    origin_node TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    causation_id TEXT,
    correlation_id TEXT,
    sequence_num INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mesh_gossip_state (
    node_id TEXT NOT NULL,
    region TEXT NOT NULL,
    last_sequence INTEGER NOT NULL DEFAULT 0,
    gossip_budget INTEGER NOT NULL DEFAULT 50,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (node_id, region)
);

CREATE TABLE IF NOT EXISTS mesh_agent_leases (
    lease_id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    holder_node TEXT NOT NULL,
    region TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mesh_memory_shards (
    shard_id TEXT PRIMARY KEY,
    region TEXT NOT NULL,
    memory_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    vector_clock TEXT NOT NULL,
    lineage_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mesh_memory_lineage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL,
    shard_id TEXT NOT NULL,
    action TEXT NOT NULL,
    node_id TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mesh_reasoning_sessions (
    session_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL,
    consensus_score REAL,
    disagreement_json TEXT,
    minority_json TEXT,
    audit_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS mesh_consensus_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    agent_id TEXT,
    vote REAL NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mesh_learning_deltas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region TEXT NOT NULL,
    node_id TEXT NOT NULL,
    delta_kind TEXT NOT NULL,
    delta_json TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mesh_resilience_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    mesh_health REAL NOT NULL DEFAULT 1.0,
    trust_decay REAL NOT NULL DEFAULT 0.0,
    quarantined_nodes_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mesh_simulation_tournaments (
    tournament_id TEXT PRIMARY KEY,
    scenario_set_json TEXT NOT NULL,
    lane TEXT NOT NULL DEFAULT 'mesh_shadow',
    status TEXT NOT NULL,
    scores_json TEXT,
    winner TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS mesh_cognitive_budgets (
    region TEXT PRIMARY KEY,
    reasoning_quota REAL NOT NULL DEFAULT 100.0,
    memory_quota REAL NOT NULL DEFAULT 1000.0,
    simulation_quota REAL NOT NULL DEFAULT 10.0,
    spent_reasoning REAL NOT NULL DEFAULT 0,
    spent_memory REAL NOT NULL DEFAULT 0,
    spent_simulation REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mesh_constitutional_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS mesh_observability_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_type TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mesh_events_region ON mesh_cognitive_events(region, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mesh_sessions_status ON mesh_reasoning_sessions(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mesh_shards_region ON mesh_memory_shards(region, memory_id);

CREATE TABLE IF NOT EXISTS epistemic_scores (
    score_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    confidence REAL NOT NULL,
    uncertainty REAL NOT NULL,
    evidence_depth REAL NOT NULL DEFAULT 0,
    contradiction_exposure REAL NOT NULL DEFAULT 0,
    source_diversity REAL NOT NULL DEFAULT 0,
    replay_stability REAL NOT NULL DEFAULT 1.0,
    explanation TEXT,
    replay_key TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_confidence_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    score_id TEXT NOT NULL,
    prior_confidence REAL NOT NULL,
    posterior_confidence REAL NOT NULL,
    delta_reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_contradictions (
    contradiction_id TEXT PRIMARY KEY,
    cluster_id TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    severity REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    explanation TEXT NOT NULL,
    minority_preserved_json TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS epistemic_contradiction_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contradiction_id TEXT NOT NULL,
    from_claim TEXT NOT NULL,
    to_claim TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    region TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_narratives (
    narrative_id TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    topic TEXT NOT NULL,
    region TEXT,
    framing_json TEXT NOT NULL,
    anomaly_score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_narrative_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    narrative_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    temporal_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_trust_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    trust_score REAL NOT NULL,
    reversible INTEGER NOT NULL DEFAULT 1,
    reason TEXT NOT NULL,
    correction_count INTEGER NOT NULL DEFAULT 0,
    contradiction_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    UNIQUE(from_node, to_node)
);

CREATE TABLE IF NOT EXISTS epistemic_trust_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_node TEXT NOT NULL,
    to_node TEXT NOT NULL,
    prior_trust REAL NOT NULL,
    new_trust REAL NOT NULL,
    action TEXT NOT NULL,
    operator_id TEXT,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_alerts (
    alert_id TEXT PRIMARY KEY,
    alert_type TEXT NOT NULL,
    severity REAL NOT NULL,
    subject_id TEXT NOT NULL,
    explanation TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending_review',
    region TEXT,
    payload_json TEXT,
    operator_validated INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_replay_runs (
    run_id TEXT PRIMARY KEY,
    lane TEXT NOT NULL DEFAULT 'epistemic',
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    stability_score REAL NOT NULL,
    divergence_score REAL NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_drift_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    drift_kind TEXT NOT NULL,
    region TEXT,
    entropy_score REAL NOT NULL,
    diversity_score REAL NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_governance_policies (
    policy_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (policy_id, version)
);

CREATE TABLE IF NOT EXISTS epistemic_calibration_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calibration_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    operator_id TEXT,
    annotation TEXT,
    prior_value REAL,
    new_value REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epistemic_observability_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_type TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_epistemic_scores_subject ON epistemic_scores(subject_type, subject_id);
CREATE INDEX IF NOT EXISTS idx_epistemic_contradictions_status ON epistemic_contradictions(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_epistemic_alerts_status ON epistemic_alerts(status, created_at DESC);

CREATE TABLE IF NOT EXISTS ops_burnin_runs (
    run_id TEXT PRIMARY KEY,
    profile TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    health_score REAL,
    summary_json TEXT
);

CREATE TABLE IF NOT EXISTS ops_burnin_samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    sample_at TEXT NOT NULL,
    metrics_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_feed_health (
    feed_url TEXT PRIMARY KEY,
    source_name TEXT,
    reliability_score REAL NOT NULL DEFAULT 0.5,
    malformed_count INTEGER NOT NULL DEFAULT 0,
    duplicate_burst INTEGER NOT NULL DEFAULT 0,
    last_success_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_certification_runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    gates_passed INTEGER NOT NULL DEFAULT 0,
    gates_failed INTEGER NOT NULL DEFAULT 0,
    report_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_incident_bundles (
    bundle_id TEXT PRIMARY KEY,
    incident_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    bundle_json TEXT NOT NULL,
    rca_summary TEXT,
    created_at TEXT NOT NULL,
    exported_at TEXT
);

CREATE TABLE IF NOT EXISTS ops_editorial_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    review_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    operator_id TEXT,
    score REAL,
    annotation TEXT,
    useful INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_cost_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region TEXT,
    token_spend REAL NOT NULL DEFAULT 0,
    replay_cost REAL NOT NULL DEFAULT 0,
    cognition_cost REAL NOT NULL DEFAULT 0,
    federation_cost REAL NOT NULL DEFAULT 0,
    anomaly_score REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_storage_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    estimated_bytes INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_alert_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 50,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    detail_json TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    escalated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_incident_threads (
    thread_id TEXT PRIMARY KEY,
    correlation_key TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    timeline_json TEXT NOT NULL,
    replay_refs_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_console_usability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivered INTEGER NOT NULL DEFAULT 0,
    suppressed INTEGER NOT NULL DEFAULT 0,
    aggregated INTEGER NOT NULL DEFAULT 0,
    fatigue_score REAL NOT NULL DEFAULT 0,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_telegram_outbound (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_key TEXT NOT NULL,
    channel_id INTEGER NOT NULL,
    success INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    telegram_message_id INTEGER,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_feed_quarantine (
    feed_url TEXT PRIMARY KEY,
    source_name TEXT,
    reason TEXT NOT NULL,
    quarantined_at TEXT NOT NULL,
    until_at TEXT
);

CREATE TABLE IF NOT EXISTS ops_incidents (
    incident_id TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'open',
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    correlation_key TEXT NOT NULL,
    detail_json TEXT,
    replay_refs_json TEXT,
    suggested_action TEXT,
    operator_id TEXT,
    acked_at TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_evidence_bundles (
    bundle_id TEXT PRIMARY KEY,
    period TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_longevity_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    period TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_telegram_outbound_created ON ops_telegram_outbound(created_at);
CREATE INDEX IF NOT EXISTS idx_ops_incidents_status ON ops_incidents(status, created_at DESC);

CREATE TABLE IF NOT EXISTS ops_compaction_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_table TEXT NOT NULL,
    rows_before INTEGER NOT NULL,
    rows_after INTEGER NOT NULL,
    policy TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_burnin_samples_run ON ops_burnin_samples(run_id, sample_at);
CREATE INDEX IF NOT EXISTS idx_ops_alert_queue_status ON ops_alert_queue(status, priority DESC);

CREATE TABLE IF NOT EXISTS ops_burnin_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    period TEXT NOT NULL,
    report_markdown TEXT NOT NULL,
    regressions_json TEXT,
    health_score REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_operator_sessions (
    session_id TEXT PRIMARY KEY,
    operator_id TEXT,
    session_type TEXT NOT NULL,
    actions_count INTEGER NOT NULL DEFAULT 0,
    fatigue_score REAL NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS ops_forensics_traces (
    trace_id TEXT PRIMARY KEY,
    story_id INTEGER,
    trace_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    correlation_id TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_forensics_story ON ops_forensics_traces(story_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ops_admin_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id TEXT NOT NULL,
    command TEXT NOT NULL,
    args_preview TEXT,
    success INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_operator_heartbeat (
    operator_id TEXT PRIMARY KEY,
    last_seen_at TEXT NOT NULL,
    last_command TEXT
);

CREATE TABLE IF NOT EXISTS ops_rollout_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    stage TEXT NOT NULL,
    previous_stage TEXT,
    rollback_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    detail_json TEXT
);

CREATE TABLE IF NOT EXISTS ops_poison_queue (
    message_key TEXT PRIMARY KEY,
    subsystem TEXT NOT NULL,
    payload_preview TEXT,
    reason TEXT NOT NULL,
    quarantined_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_epistemic_longitudinal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_at TEXT NOT NULL,
    confidence_mean REAL,
    uncertainty_mean REAL,
    open_contradictions INTEGER NOT NULL DEFAULT 0,
    misinfo_pressure REAL NOT NULL DEFAULT 0,
    diversity_score REAL NOT NULL DEFAULT 0,
    alerts_json TEXT
);

CREATE TABLE IF NOT EXISTS ops_replay_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    subject_type TEXT NOT NULL,
    subject_id TEXT NOT NULL,
    sequence_watermark INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    tier TEXT NOT NULL DEFAULT 'hot',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_readiness_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    staging_score REAL NOT NULL,
    certification_passed INTEGER NOT NULL,
    burnin_health REAL,
    epistemic_stability REAL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_daily_cost_reports (
    report_date TEXT PRIMARY KEY,
    total_usd REAL NOT NULL,
    breakdown_json TEXT NOT NULL,
    anomaly INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_staging_publish_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    correlation_id TEXT NOT NULL,
    pending_news_id INTEGER,
    channel_id INTEGER,
    approved INTEGER NOT NULL DEFAULT 0,
    operator_id TEXT,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_staging_publish_corr ON ops_staging_publish_audit(correlation_id);

CREATE TABLE IF NOT EXISTS ops_chaos_runs (
    run_id TEXT PRIMARY KEY,
    scenario TEXT NOT NULL,
    status TEXT NOT NULL,
    survivability_score REAL NOT NULL,
    detail_json TEXT,
    started_at TEXT NOT NULL,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS ops_slo_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slo_name TEXT NOT NULL,
    window_hours REAL NOT NULL,
    compliance_ratio REAL NOT NULL,
    burn_rate REAL NOT NULL,
    error_budget_remaining REAL NOT NULL,
    violated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_slo_name_time ON ops_slo_snapshots(slo_name, created_at DESC);

CREATE TABLE IF NOT EXISTS ops_certification_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL,
    score REAL NOT NULL,
    blockers_json TEXT,
    certified_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_audit_chain (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    action_id TEXT NOT NULL UNIQUE,
    operator_id TEXT NOT NULL,
    command TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    chain_hash TEXT NOT NULL,
    signature TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_governance_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    editorial_frozen INTEGER NOT NULL DEFAULT 0,
    quarantine_depth INTEGER NOT NULL DEFAULT 0,
    consensus_required INTEGER NOT NULL DEFAULT 0,
    sensitive_topics_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_executive_reports (
    report_id TEXT PRIMARY KEY,
    report_type TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_rc1_config_fingerprint (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    fingerprint TEXT NOT NULL,
    config_json TEXT NOT NULL,
    issues_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_rc1_activation (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    stage TEXT NOT NULL,
    previous_stage TEXT,
    operator_signoff TEXT,
    snapshot_json TEXT,
    rollback_point TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_rc1_baselines (
    metric_name TEXT PRIMARY KEY,
    mean_value REAL NOT NULL,
    std_value REAL NOT NULL,
    sample_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_rc1_runtime_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_rc1_validation_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    go_live_confidence REAL NOT NULL,
    publish_integrity REAL NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_ga_traffic_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    pressure_level TEXT NOT NULL,
    publishes_hour INTEGER NOT NULL DEFAULT 0,
    global_freeze INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_ga_quality_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER,
    pending_news_id INTEGER,
    headline_score REAL,
    consistency_score REAL,
    contradiction_score REAL,
    toxicity_score REAL,
    readability_score REAL,
    overall_score REAL NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_ga_quality_story ON ops_ga_quality_scores(story_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ops_ga_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT,
    channel_id INTEGER,
    feedback_type TEXT NOT NULL,
    impact_score REAL NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_ga_readiness (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    state TEXT NOT NULL,
    score REAL NOT NULL,
    blockers_json TEXT,
    evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_ga_rollback_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    stage TEXT NOT NULL,
    integrity_hash TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_ga_retention_runs (
    run_id TEXT PRIMARY KEY,
    policy TEXT NOT NULL,
    rows_affected INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_post_ga_calibration (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    audience_responsiveness REAL NOT NULL,
    publish_efficiency REAL NOT NULL,
    pacing_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_post_ga_quality_learning (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_key TEXT,
    pattern_type TEXT NOT NULL,
    score REAL NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_post_ga_stability (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    autonomy_score REAL NOT NULL,
    fatigue_index REAL NOT NULL,
    detail_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_post_ga_optimization (
    proposal_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    change_json TEXT NOT NULL,
    explain_text TEXT NOT NULL,
    status TEXT NOT NULL,
    operator_id TEXT,
    created_at TEXT NOT NULL,
    applied_at TEXT
);

CREATE TABLE IF NOT EXISTS ops_post_ga_risk_forecast (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horizon_hours REAL NOT NULL,
    overload_prob REAL NOT NULL,
    slo_violation_prob REAL NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_post_ga_governance (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    trust_trajectory_json TEXT,
    policy_snapshot_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_evolution_memory (
    memory_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    confidence REAL NOT NULL,
    outcome TEXT,
    similarity_key TEXT,
    created_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ops_evolution_memory_cat ON ops_evolution_memory(category, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_evolution_memory_key ON ops_evolution_memory(similarity_key);

CREATE TABLE IF NOT EXISTS ops_evolution_strategy (
    proposal_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    title TEXT NOT NULL,
    impact_estimate REAL NOT NULL,
    confidence REAL NOT NULL,
    tradeoffs_json TEXT,
    explain_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_evolution_maturity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_json TEXT NOT NULL,
    overall_score REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_evolution_analytics (
    period TEXT NOT NULL,
    period_key TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    sustainability_score REAL NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (period, period_key)
);

CREATE TABLE IF NOT EXISTS ops_evolution_maintenance (
    plan_id TEXT PRIMARY KEY,
    window_utc TEXT NOT NULL,
    tasks_json TEXT NOT NULL,
    risk_score REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_evolution_safety (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evolution_risk REAL NOT NULL,
    drift_flags_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_plugins (
    plugin_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    version TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    capabilities_json TEXT NOT NULL,
    health_status TEXT NOT NULL DEFAULT 'unknown',
    enabled INTEGER NOT NULL DEFAULT 1,
    trust_score REAL NOT NULL DEFAULT 0.5,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_plugin_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_workflow_defs (
    workflow_name TEXT PRIMARY KEY,
    definition_json TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_graph_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_type TEXT NOT NULL,
    from_id TEXT NOT NULL,
    to_type TEXT NOT NULL,
    to_id TEXT NOT NULL,
    relation TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_platform_graph_from ON platform_graph_edges(from_type, from_id);
CREATE INDEX IF NOT EXISTS idx_platform_graph_to ON platform_graph_edges(to_type, to_id);

CREATE TABLE IF NOT EXISTS platform_policies (
    policy_id TEXT PRIMARY KEY,
    domain TEXT NOT NULL,
    version INTEGER NOT NULL,
    policy_json TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_api_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint TEXT NOT NULL,
    scope TEXT NOT NULL,
    caller TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS platform_inventory (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    snapshot_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS go_live_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    publication_stage TEXT NOT NULL DEFAULT 'INTERNAL_SHADOW',
    rollout_stage TEXT NOT NULL DEFAULT 'INTERNAL_SHADOW',
    operator_signoff TEXT,
    snapshot_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_shift_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    owner_operator_id TEXT,
    started_at TEXT,
    handoff_json TEXT,
    unresolved_warnings_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_shift_ack (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operator_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_war_room (
    incident_id TEXT PRIMARY KEY,
    active INTEGER NOT NULL DEFAULT 1,
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    timeline_json TEXT,
    telemetry_json TEXT,
    rollback_recommendation TEXT,
    checklist_json TEXT,
    notes_json TEXT
);

CREATE TABLE IF NOT EXISTS ops_campaign_mode (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active INTEGER NOT NULL DEFAULT 0,
    campaign_type TEXT,
    started_at TEXT,
    config_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_reputation_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_reputation REAL NOT NULL,
    trust_volatility REAL NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_audit_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    findings_json TEXT NOT NULL,
    compliance_score REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_launch_period (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    production_start_at TEXT NOT NULL,
    launch_risk_score REAL NOT NULL DEFAULT 0.5,
    protections_active INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_drill_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    score REAL NOT NULL,
    detail_json TEXT,
    simulated INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_rhythm_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rhythm_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_live_deploy_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    production_start_at TEXT NOT NULL,
    first_72h_active INTEGER NOT NULL DEFAULT 1,
    reports_sent_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_live_deploy_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER,
    action TEXT NOT NULL,
    passed INTEGER NOT NULL,
    blockers_json TEXT NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_live_deploy_drills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scenario TEXT NOT NULL,
    score REAL NOT NULL,
    response_ms INTEGER NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS week1_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    week_start_at TEXT NOT NULL,
    baseline_captured INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS week1_baselines (
    domain TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    captured_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS week1_alert_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key TEXT NOT NULL,
    severity TEXT NOT NULL,
    root_cause TEXT,
    confidence REAL NOT NULL,
    suppressed INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS week1_quality_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quality_score REAL NOT NULL,
    fatigue_score REAL NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS week1_optimization_proposals (
    proposal_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    safety_score REAL NOT NULL,
    blast_radius TEXT NOT NULL,
    approved INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS week1_survivability (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    survivability_score REAL NOT NULL,
    confidence_trend REAL NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opmem_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL UNIQUE,
    incident_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    duration_sec REAL,
    affected_subsystems_json TEXT NOT NULL,
    metrics_snapshot_json TEXT NOT NULL,
    survivability_score REAL,
    confidence_trend REAL,
    root_cause_candidate TEXT,
    operator_actions_json TEXT,
    recovery_duration_sec REAL,
    fingerprint_hash TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_opmem_incidents_type ON opmem_incidents(incident_type, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_opmem_incidents_fp ON opmem_incidents(fingerprint_hash);

CREATE TABLE IF NOT EXISTS opmem_fingerprints (
    signature_hash TEXT PRIMARY KEY,
    pattern_name TEXT NOT NULL,
    confidence REAL NOT NULL,
    recurrence_count INTEGER NOT NULL DEFAULT 1,
    last_seen_at TEXT NOT NULL,
    avg_impact REAL NOT NULL DEFAULT 0,
    typical_recovery_sec REAL,
    detail_json TEXT
);

CREATE TABLE IF NOT EXISTS opmem_predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horizon TEXT NOT NULL,
    risk_degradation REAL NOT NULL,
    risk_rollback REAL NOT NULL,
    risk_queue_overflow REAL NOT NULL,
    risk_alert_storm REAL NOT NULL,
    risk_audience_fatigue REAL NOT NULL,
    explain_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_opmem_predictions_horizon ON opmem_predictions(horizon, created_at DESC);

CREATE TABLE IF NOT EXISTS opmem_drift_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain TEXT NOT NULL,
    drift_score REAL NOT NULL,
    systemic INTEGER NOT NULL DEFAULT 0,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opmem_seasonality_profiles (
    bucket_key TEXT PRIMARY KEY,
    profile_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opmem_recommendations (
    proposal_id TEXT PRIMARY KEY,
    recommendation TEXT NOT NULL,
    expected_impact TEXT NOT NULL,
    blast_radius TEXT NOT NULL,
    rollback_safe INTEGER NOT NULL DEFAULT 1,
    confidence REAL NOT NULL,
    similar_incidents_json TEXT,
    approved INTEGER NOT NULL DEFAULT 0,
    outcome TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS opmem_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    retention_days INTEGER NOT NULL DEFAULT 90,
    last_prune_at TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_channel_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    live_mode TEXT NOT NULL DEFAULT 'shadow',
    paused INTEGER NOT NULL DEFAULT 0,
    frozen INTEGER NOT NULL DEFAULT 0,
    publishes_this_hour INTEGER NOT NULL DEFAULT 0,
    hour_bucket TEXT,
    failures_recent INTEGER NOT NULL DEFAULT 0,
    cooldown_until TEXT,
    last_rollback_at TEXT,
    trust_score REAL NOT NULL DEFAULT 0.85,
    content_stability_score REAL NOT NULL DEFAULT 0.9,
    detail_json TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_channel_publish_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER NOT NULL,
    channel_id INTEGER,
    live_mode TEXT NOT NULL,
    action TEXT NOT NULL,
    passed INTEGER NOT NULL,
    blockers_json TEXT,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_channel_publish_log_ts
    ON live_channel_publish_log(created_at DESC);

CREATE TABLE IF NOT EXISTS live_channel_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_channel_post_ratings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER NOT NULL,
    rating TEXT NOT NULL,
    operator_id INTEGER,
    note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_channel_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_publish_trace (
    post_id TEXT PRIMARY KEY,
    pending_news_id INTEGER NOT NULL,
    trace_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_publish_trace_ts ON live_publish_trace(created_at DESC);

CREATE TABLE IF NOT EXISTS live_source_quarantine (
    source TEXT PRIMARY KEY,
    bad_count_24h INTEGER NOT NULL DEFAULT 0,
    cooldown_until TEXT,
    mode TEXT NOT NULL DEFAULT 'shadow',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_metrics_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_metrics_snapshots_ts ON live_metrics_snapshots(created_at DESC);

CREATE TABLE IF NOT EXISTS live_incident_timeline (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    runtime_instance_id TEXT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    correlation_id TEXT,
    publish_id TEXT,
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_incident_timeline_ts
    ON live_incident_timeline(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_live_incident_timeline_corr
    ON live_incident_timeline(correlation_id);
CREATE INDEX IF NOT EXISTS idx_live_incident_timeline_publish
    ON live_incident_timeline(publish_id);
CREATE INDEX IF NOT EXISTS idx_live_incident_timeline_type
    ON live_incident_timeline(event_type, timestamp DESC);

CREATE TABLE IF NOT EXISTS live_operational_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT,
    runtime_instance_id TEXT,
    correlation_id TEXT,
    publish_id TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_live_operational_audit_ts
    ON live_operational_audit(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_live_operational_audit_publish
    ON live_operational_audit(publish_id);

CREATE TABLE IF NOT EXISTS runtime_state_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    runtime_instance_id TEXT,
    runtime_profile TEXT,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runtime_state_snapshot_ts
    ON runtime_state_snapshot(timestamp DESC);

CREATE TABLE IF NOT EXISTS ops_runtime_baseline (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    locked_at TEXT NOT NULL,
    baseline_json TEXT NOT NULL,
    notes TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_incident_bundle (
    bundle_id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    export_path TEXT NOT NULL,
    summary_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editorial_quality_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER NOT NULL,
    editorial_quality_score REAL NOT NULL,
    dimensions_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    fatigue_json TEXT NOT NULL,
    drift_json TEXT NOT NULL,
    headline TEXT,
    summary TEXT,
    source TEXT,
    template_key TEXT,
    tags_json TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_editorial_quality_pending
    ON editorial_quality_scores(pending_news_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_editorial_quality_ts
    ON editorial_quality_scores(created_at DESC);

CREATE TABLE IF NOT EXISTS editorial_phrase_stats (
    phrase TEXT PRIMARY KEY,
    count_7d INTEGER NOT NULL DEFAULT 0,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editorial_quality_daily (
    date TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS editorial_storylines (
    storyline_id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    title TEXT NOT NULL,
    topic_keys_json TEXT NOT NULL,
    entity_keys_json TEXT NOT NULL DEFAULT '[]',
    first_seen_at TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    publish_count INTEGER NOT NULL DEFAULT 0,
    source_diversity_json TEXT NOT NULL DEFAULT '[]',
    latest_headline TEXT,
    latest_summary TEXT,
    tone_direction TEXT,
    unresolved_json TEXT NOT NULL DEFAULT '[]',
    saturation_score REAL NOT NULL DEFAULT 0,
    cluster_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_editorial_storylines_updated
    ON editorial_storylines(last_updated_at DESC);

CREATE TABLE IF NOT EXISTS editorial_story_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    storyline_id TEXT NOT NULL,
    pending_news_id INTEGER,
    event_type TEXT NOT NULL,
    follow_up_kind TEXT NOT NULL,
    headline TEXT NOT NULL,
    summary TEXT,
    source TEXT,
    tags_json TEXT,
    context_snippet TEXT,
    contradiction_flags_json TEXT NOT NULL DEFAULT '[]',
    novelty_score REAL NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_editorial_story_events_storyline
    ON editorial_story_events(storyline_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_editorial_story_events_pending
    ON editorial_story_events(pending_news_id);

CREATE TABLE IF NOT EXISTS editorial_priority_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER NOT NULL,
    editorial_priority_score REAL NOT NULL,
    urgency_class TEXT NOT NULL,
    factors_json TEXT NOT NULL,
    warnings_json TEXT NOT NULL,
    momentum_json TEXT NOT NULL,
    balance_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_editorial_priority_pending
    ON editorial_priority_scores(pending_news_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_editorial_priority_ts
    ON editorial_priority_scores(created_at DESC);

CREATE TABLE IF NOT EXISTS editorial_priority_daily (
    date TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_attention_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    bundled_count INTEGER NOT NULL DEFAULT 1,
    delivered INTEGER NOT NULL DEFAULT 0,
    suppressed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_attention_log_fp
    ON ops_attention_log(fingerprint, last_seen_at DESC);

CREATE TABLE IF NOT EXISTS ops_attention_daily (
    date TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_lifecycle_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_type TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_lifecycle_runs_ts
    ON ops_lifecycle_runs(created_at DESC);

CREATE TABLE IF NOT EXISTS ops_lifecycle_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    last_maintenance_at TEXT,
    last_vacuum_at TEXT,
    last_backup_at TEXT,
    state_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_lifecycle_daily (
    date TEXT NOT NULL,
    category TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (date, category)
);

CREATE TABLE IF NOT EXISTS ops_trust_calibration_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER,
    subsystem TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    signal_value TEXT,
    operator_action TEXT,
    outcome TEXT,
    detail_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_trust_events_subsystem
    ON ops_trust_calibration_events(subsystem, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ops_trust_events_pending
    ON ops_trust_calibration_events(pending_news_id);

CREATE TABLE IF NOT EXISTS ops_trust_subsystem_daily (
    date TEXT NOT NULL,
    subsystem TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    trust_band TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (date, subsystem)
);

CREATE TABLE IF NOT EXISTS ops_trust_calibration_daily (
    date TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_evidence_reviews (
    week_id TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    confidence_band TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_evidence_reviews_created
    ON ops_evidence_reviews(created_at DESC);

CREATE TABLE IF NOT EXISTS ops_resilience_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    posture TEXT NOT NULL,
    posture_reason TEXT,
    dependencies_json TEXT NOT NULL,
    budgets_json TEXT NOT NULL,
    backpressure_json TEXT NOT NULL,
    guidance_json TEXT NOT NULL,
    forecast_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_resilience_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    subsystem TEXT,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ops_resilience_events_type
    ON ops_resilience_events(event_type, created_at DESC);

CREATE TABLE IF NOT EXISTS ops_resilience_recovery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subsystem TEXT NOT NULL,
    outcome TEXT NOT NULL,
    duration_sec REAL,
    detail_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_resilience_daily (
    date TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_consolidation_snapshots (
    date TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    complexity_score REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_publish_funnel_hourly (
    hour_key TEXT PRIMARY KEY,
    counters_json TEXT NOT NULL,
    rejection_reasons_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_flow_health_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    recovery_activated_at TEXT,
    metrics_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ops_duplicate_escape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pending_news_id INTEGER NOT NULL,
    headline TEXT,
    cluster_id INTEGER,
    source TEXT,
    slipped_through INTEGER NOT NULL DEFAULT 0,
    context_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_MIGRATIONS = (
    ("cluster_id", "ALTER TABLE pending_news ADD COLUMN cluster_id INTEGER"),
    ("priority_score", "ALTER TABLE pending_news ADD COLUMN priority_score REAL DEFAULT 0"),
    ("priority_reason", "ALTER TABLE pending_news ADD COLUMN priority_reason TEXT"),
    ("source_count", "ALTER TABLE pending_news ADD COLUMN source_count INTEGER DEFAULT 1"),
    ("media_type", "ALTER TABLE pending_news ADD COLUMN media_type TEXT DEFAULT 'none'"),
    ("media_url", "ALTER TABLE pending_news ADD COLUMN media_url TEXT"),
    ("thumbnail_url", "ALTER TABLE pending_news ADD COLUMN thumbnail_url TEXT"),
    ("media_width", "ALTER TABLE pending_news ADD COLUMN media_width INTEGER"),
    ("media_height", "ALTER TABLE pending_news ADD COLUMN media_height INTEGER"),
    ("optimized_headline", "ALTER TABLE pending_news ADD COLUMN optimized_headline TEXT"),
    ("hook_line", "ALTER TABLE pending_news ADD COLUMN hook_line TEXT"),
    ("caption_style", "ALTER TABLE pending_news ADD COLUMN caption_style TEXT DEFAULT 'optimized'"),
    ("source_language", "ALTER TABLE pending_news ADD COLUMN source_language TEXT DEFAULT 'en'"),
    ("target_language", "ALTER TABLE pending_news ADD COLUMN target_language TEXT"),
    ("translated_title", "ALTER TABLE pending_news ADD COLUMN translated_title TEXT"),
    ("translated_summary", "ALTER TABLE pending_news ADD COLUMN translated_summary TEXT"),
    ("localized_headline", "ALTER TABLE pending_news ADD COLUMN localized_headline TEXT"),
    ("localized_hook", "ALTER TABLE pending_news ADD COLUMN localized_hook TEXT"),
    ("published_posts_language", "ALTER TABLE published_posts ADD COLUMN language TEXT DEFAULT 'en'"),
    ("digests_language", "ALTER TABLE digests ADD COLUMN language TEXT DEFAULT 'en'"),
    ("entities_canonical_key", "ALTER TABLE entities ADD COLUMN canonical_key TEXT"),
    ("story_id", "ALTER TABLE pending_news ADD COLUMN story_id INTEGER"),
)


def default_db_path() -> Path:
    return project_root() / _DB_FILENAME


def init_database(db_path: Path | None = None) -> Path:
    """Create database file and `seen_links` table if missing."""
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.executescript(_SCHEMA)
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(pending_news)").fetchall()
        }
        for column_name, statement in _MIGRATIONS:
            if column_name in columns:
                continue
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass
        conn.commit()
    return path
