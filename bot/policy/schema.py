from __future__ import annotations

from bot.policy.types import ClusterPolicyDocument

DEFAULT_CLUSTER_POLICY = ClusterPolicyDocument(
    policy_id="cluster-ops-default",
    version=1,
    node_admission={
        "min_capability_version": 1,
        "reject_draining": True,
        "max_offline_ratio": 0.5,
    },
    workflow_throttle={
        "max_concurrent_per_node": 8,
        "global_backlog_threshold": 500,
        "shed_analytics_above_backlog": 300,
    },
    regional_failover={
        "preferred_regions": ["eu", "us", "global"],
        "min_healthy_nodes_per_region": 1,
        "failover_score_threshold": 0.4,
    },
    publish_limits={
        "max_per_minute": 30,
        "burst_allowance": 5,
        "publish_safe_backlog": 400,
    },
    retry_escalation={
        "max_transient_retries": 5,
        "base_delay_sec": 2.0,
        "max_delay_sec": 120.0,
        "permanent_error_patterns": ["invalid_token", "forbidden", "chat_not_found"],
    },
    quarantine_rules={
        "max_event_retries": 5,
        "max_workflow_failures": 3,
        "noisy_node_error_rate": 0.35,
    },
    federation_sync={
        "enabled": True,
        "pause_below_region_score": 0.3,
        "max_sync_keys_per_cycle": 32,
    },
    digest_priority={
        "breaking_preempts_digest": True,
        "min_qos_class": "digest",
        "lease_weight_breaking": 3.0,
        "lease_weight_digest": 1.0,
    },
    maintenance_windows=[],
    degradation_triggers={
        "queue_backlog": 500,
        "stream_lag_sec": 30.0,
        "dlq_count": 100,
        "region_score": 0.35,
        "workflow_stalled": 5,
    },
)
