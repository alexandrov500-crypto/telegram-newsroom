from __future__ import annotations

from bot.operator_ux.dedupe import AlertBundler, AttentionItem, bundle_runtime_signals
from bot.operator_ux.quiet import should_deliver
from bot.operator_ux.severity import (
    AttentionSeverity,
    classify_editorial_warning,
    classify_runtime_anomaly,
)
from bot.operator_ux.compress import compress_priority_rationale


def test_severity_mapping() -> None:
    assert classify_runtime_anomaly({"level": "critical"}) == AttentionSeverity.CRITICAL
    assert classify_editorial_warning("framing differs significantly") == AttentionSeverity.IMPORTANT


def test_quiet_critical_bypass() -> None:
    assert should_deliver(AttentionSeverity.CRITICAL, force=False) is True


def test_alert_deduplication() -> None:
    bundler = AlertBundler(window_minutes=20)
    a = AttentionItem(AttentionSeverity.IMPORTANT, "runtime", "lag spike")
    first = bundler.add(a)
    second = bundler.add(
        AttentionItem(AttentionSeverity.IMPORTANT, "runtime", "lag spike"),
    )
    assert first is not None
    assert second is None
    assert bundler.suppressed_total >= 1


def test_runtime_bundle_line() -> None:
    lines = bundle_runtime_signals(
        {
            "event_loop_lag_max": 0.22,
            "stalled_loops": ["a", "b"],
            "recovery_attempt_count": 1,
        },
    )
    assert lines
    assert "Runtime instability" in lines[0]


def test_compress_rationale() -> None:
    text = compress_priority_rationale(
        headline="Fed holds rates",
        urgency="significant",
        why=["multi-source corroboration", "high-signal entities (Fed)"],
        storyline_id="sl-inflation-fed",
        follow_up="follow_up",
    )
    assert "Fed" in text or "multi-source" in text
    assert "{" not in text
