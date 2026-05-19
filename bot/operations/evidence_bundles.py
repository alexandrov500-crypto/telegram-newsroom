from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.operations.repository import OperationsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    period: str
    payload: dict[str, Any]
    markdown: str


class ContinuousEvidenceGenerator:
    """Deterministic 6h operational evidence for long-running staging."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    def build_bundle(self, *, signals: dict[str, Any], ops_report: dict[str, Any]) -> EvidenceBundle:
        now = datetime.now(timezone.utc)
        bundle_id = f"ev_{now.strftime('%Y%m%d%H')}"
        active = self._repo.active_burnin()
        open_incidents = self._repo.list_incidents(status="open", limit=20)
        payload = {
            "bundle_id": bundle_id,
            "generated_at": now.isoformat(),
            "period": "6h",
            "burnin_run": active.get("run_id") if active else None,
            "replay_health": ops_report.get("replay_divergence"),
            "long_run_health": ops_report.get("long_run_health"),
            "open_contradictions": signals.get("open_contradictions", 0),
            "mesh_health": signals.get("mesh_health", 1.0),
            "queue_backlog": signals.get("queue_backlog", 0),
            "operator_fatigue": ops_report.get("operator_fatigue"),
            "telegram_delivery_failures": self._repo.telegram_delivery_failure_count(hours=6),
            "storage_growth_mb_day": signals.get("storage_growth_mb_day", 0),
            "open_incidents": len(open_incidents),
            "loop_health": signals.get("loop_health", {}),
        }
        md = self._format_markdown(payload, open_incidents)
        return EvidenceBundle(bundle_id=bundle_id, period="6h", payload=payload, markdown=md)

    def persist(
        self,
        bundle: EvidenceBundle,
        *,
        json_dir: Path | None = None,
        markdown_path: Path | None = None,
    ) -> tuple[Path | None, Path | None]:
        json_dir = json_dir or Path("artifacts/operations")
        markdown_path = markdown_path or Path("docs/BURN_IN_REPORT.md")
        json_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_dir / f"{bundle.bundle_id}.json"
        json_path.write_text(json.dumps(bundle.payload, indent=2), encoding="utf-8")
        self._repo.save_evidence_bundle(bundle.bundle_id, bundle.period, bundle.payload)
        try:
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(bundle.markdown, encoding="utf-8")
        except OSError:
            logger.debug("event=evidence_markdown_write_skipped")
            markdown_path = None
        return json_path, markdown_path

    @staticmethod
    def _format_markdown(payload: dict[str, Any], incidents: list[dict]) -> str:
        lines = [
            "# Burn-in operational evidence (6h)",
            "",
            f"Generated: {payload['generated_at']}",
            f"Bundle: `{payload['bundle_id']}`",
            "",
            "## Summary",
            f"- Replay divergence: **{payload.get('replay_health', 'n/a')}**",
            f"- Long-run health: **{payload.get('long_run_health', 'n/a')}**",
            f"- Open contradictions: **{payload.get('open_contradictions', 0)}**",
            f"- Mesh health: **{payload.get('mesh_health', 1.0):.2f}**",
            f"- Queue backlog: **{payload.get('queue_backlog', 0)}**",
            f"- Operator fatigue: **{payload.get('operator_fatigue', 'n/a')}**",
            f"- Telegram delivery failures (6h): **{payload.get('telegram_delivery_failures', 0)}**",
            f"- Storage growth (MB/day): **{payload.get('storage_growth_mb_day', 0)}**",
            f"- Open incidents: **{payload.get('open_incidents', 0)}**",
            "",
            "## Incidents",
        ]
        if not incidents:
            lines.append("_No open incidents._")
        else:
            for inc in incidents[:8]:
                lines.append(
                    f"- `{inc.get('incident_id', '?')}` {inc.get('title', '')} "
                    f"({inc.get('severity', '')})"
                )
        lines.append("")
        lines.append("_Replay-linked · archaeology-compatible_")
        return "\n".join(lines)
