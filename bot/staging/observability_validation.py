from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_EXPECTED_METRICS = (
    "queue_backlog",
    "articles_ingested_total",
    "telegram_publish_success_total",
    "burnin_health_score",
)


@dataclass(frozen=True)
class TelemetryHealthReport:
    passed: bool
    present: tuple[str, ...]
    missing: tuple[str, ...]
    tracing_enabled: bool
    otlp_configured: bool

    def summary(self) -> str:
        lines = ["Telemetry health:"]
        lines.append(f"  Tracing: {'on' if self.tracing_enabled else 'off'}")
        lines.append(f"  OTLP: {'configured' if self.otlp_configured else 'not configured'}")
        if self.missing:
            lines.append(f"  Missing metrics: {', '.join(self.missing)}")
        else:
            lines.append("  Core metrics: OK")
        lines.append(f"  Status: {'OK' if self.passed else 'WARN'}")
        return "\n".join(lines)


def validate_startup_telemetry(*, metrics_enabled: bool) -> TelemetryHealthReport:
    present: list[str] = []
    missing: list[str] = []
    if metrics_enabled:
        try:
            from prometheus_client import REGISTRY

            names = set()
            for metric in REGISTRY.collect():
                names.add(metric.name)
            for expected in _EXPECTED_METRICS:
                if any(expected in n for n in names):
                    present.append(expected)
                else:
                    missing.append(expected)
        except Exception as exc:
            logger.warning("event=telemetry_validation_failed error=%s", exc)
            missing = list(_EXPECTED_METRICS)
    else:
        missing = list(_EXPECTED_METRICS)

    from bot.observability import tracing

    otlp = bool(__import__("os").getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())
    return TelemetryHealthReport(
        passed=len(missing) == 0 or not metrics_enabled,
        present=tuple(present),
        missing=tuple(missing),
        tracing_enabled=tracing.is_enabled(),
        otlp_configured=otlp,
    )
