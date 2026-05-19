from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from bot.platform.repository import PlatformRepository


@dataclass
class PolicyEngine:
    """Declarative policies with versioning and dry-run simulation."""

    repository: PlatformRepository
    _cache: dict[str, dict[str, Any]] = field(default_factory=dict)

    def bootstrap_defaults(self) -> None:
        defaults = (
            ("rollout", {"max_traffic_pct": 100, "require_approval_above": 50}),
            ("publish", {"min_quality_score": 0.7, "block_on_incident": True}),
            ("budget", {"daily_llm_usd": 50.0, "alert_at_pct": 80}),
            ("moderation", {"auto_hold_threshold": 0.4}),
            ("escalation", {"pager_on_severity": ["critical", "high"]}),
        )
        for kind, body in defaults:
            self.repository.save_policy(
                policy_id=f"{kind}:1",
                domain=kind,
                version=1,
                policy=body,
            )

    def get(self, kind: str) -> dict[str, Any]:
        if kind in self._cache:
            return self._cache[kind]
        rows = self.repository.active_policies(domain=kind)
        if rows:
            self._cache[kind] = rows[0]["policy"]
            return self._cache[kind]
        return {}

    def simulate(self, kind: str, context: dict[str, Any]) -> dict[str, Any]:
        policy = self.get(kind)
        if kind == "publish":
            score = float(context.get("quality_score", 0))
            allowed = score >= float(policy.get("min_quality_score", 0.7))
            return {"allowed": allowed, "reason": "quality_gate", "policy": policy}
        if kind == "budget":
            spent = float(context.get("spent_usd", 0))
            cap = float(policy.get("daily_llm_usd", 50))
            return {"allowed": spent < cap, "remaining": cap - spent}
        return {"allowed": True, "policy": policy}

    def drift_check(self) -> list[str]:
        issues: list[str] = []
        for kind in ("rollout", "publish", "budget"):
            p = self.get(kind)
            if not p:
                issues.append(f"missing:{kind}")
        return issues

    def status_text(self) -> str:
        rows = self.repository.active_policies()
        lines = ["<b>Policy status</b>"]
        for r in rows[:8]:
            lines.append(f"• {r['domain']} v{r['version']}")
        drift = self.drift_check()
        if drift:
            lines.append(f"Drift: {', '.join(drift)}")
        else:
            lines.append("Drift: none")
        return "\n".join(lines)

    def diff_text(self, kind: str = "publish") -> str:
        rows = self.repository.policy_history(kind, limit=2)
        if len(rows) < 2:
            current = self.get(kind)
            return (
                f"<b>Policy diff</b> {kind}\n"
                f"Single version v1\n"
                f"<code>{json.dumps(current)[:120]}</code>"
            )
        a, b = rows[0], rows[1]
        return (
            f"<b>Policy diff</b> {kind}\n"
            f"v{b['version']} → v{a['version']}\n"
            f"Current: <code>{json.dumps(a['policy'])[:120]}</code>"
        )
