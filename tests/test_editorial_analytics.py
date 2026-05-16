from __future__ import annotations

from utils.editorial_analytics import (
    export_editorial_analytics,
    record_moderation_publish_latency_sec,
    record_publish_attempt_count,
    reset_editorial_analytics_for_tests,
)
from utils.metrics import reset_metrics


def test_editorial_analytics_export() -> None:
    reset_metrics()
    reset_editorial_analytics_for_tests()
    record_moderation_publish_latency_sec(12.5)
    record_moderation_publish_latency_sec(14.0)
    record_publish_attempt_count(2)
    m = {"drafts_created": 10, "publishes": 4, "drafts_rejected": 1, "skipped_duplicates": 2, "publish_failures": 1}
    ed = export_editorial_analytics(m)
    assert ed["moderation_latency_samples"] == 2
    assert ed["publish_success_rate"] == 0.8
    assert ed["rejection_rate"] == 0.2
