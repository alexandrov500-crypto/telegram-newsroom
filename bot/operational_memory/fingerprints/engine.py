from __future__ import annotations

import hashlib
from typing import Any

from bot.operational_memory.repository import OperationalMemoryRepository


_PATTERN_MAP = {
    "queue": "queue_growth",
    "telegram": "publish_latency_rise",
    "retry": "retries_spike",
    "cognition": "source_timeout",
    "engagement": "low_engagement_cluster",
}


class FingerprintEngine:
    def __init__(self, repository: OperationalMemoryRepository) -> None:
        self.repository = repository

    def derive(self, incident_type: str, signals: dict[str, Any]) -> tuple[str, str]:
        """Return (signature_hash, pattern_name)."""
        parts: list[str] = [incident_type]
        for key, pattern in _PATTERN_MAP.items():
            if key in str(signals.get("degraded_subsystems", [])) or (
                key == "queue" and int(signals.get("queue_depth", 0)) > 100
            ):
                parts.append(pattern)
        if float(signals.get("retry_amplification", 0)) > 0.1:
            parts.append("retries_spike")
        name = parts[1] if len(parts) > 1 else incident_type
        sig = hashlib.sha256(":".join(sorted(parts)).encode()).hexdigest()[:16]
        return sig, name

    def register_from_incident(
        self,
        *,
        incident_type: str,
        signals: dict[str, Any],
        impact: float,
        recovery_sec: float | None,
    ) -> dict[str, Any]:
        sig, name = self.derive(incident_type, signals)
        conf = min(0.95, 0.5 + impact * 0.3)
        self.repository.upsert_fingerprint(
            signature_hash=sig,
            pattern_name=name,
            confidence=conf,
            avg_impact=impact,
            typical_recovery_sec=recovery_sec,
            detail={"incident_type": incident_type},
        )
        return self.repository.get_fingerprint(sig) or {}

    def html_detail(self, signature_hash: str) -> str:
        fp = self.repository.get_fingerprint(signature_hash)
        if not fp:
            return f"No fingerprint <code>{signature_hash}</code>"
        return (
            f"<b>Fingerprint</b> <code>{signature_hash}</code>\n"
            f"Pattern: {fp['pattern_name']}\n"
            f"Recurrence: {fp['recurrence_count']} · confidence {fp['confidence']:.0%}\n"
            f"Avg impact: {fp['avg_impact']:.2f} · recovery {fp.get('typical_recovery_sec', '?')}s"
        )
