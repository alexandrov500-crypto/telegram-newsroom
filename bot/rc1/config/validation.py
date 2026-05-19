from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.rc1.config.registry import NewsroomConfigRegistry


@dataclass(frozen=True)
class ConfigValidationIssue:
    severity: str
    code: str
    message: str
    remediation: str


@dataclass
class ConfigValidationReport:
    passed: bool
    fingerprint: str
    issues: tuple[ConfigValidationIssue, ...]
    incompatible_pairs: tuple[str, ...]

    def summary_lines(self) -> list[str]:
        lines = [f"Fingerprint: <code>{self.fingerprint}</code>"]
        if self.passed:
            lines.append("✅ Config validation passed")
        else:
            lines.append("⛔ Config validation failed")
        for issue in self.issues[:8]:
            mark = "🚨" if issue.severity == "error" else "⚠️"
            lines.append(f"{mark} {issue.code}: {issue.message[:70]}")
            lines.append(f"   → {issue.remediation[:80]}")
        return lines


class ConfigValidationGraph:
    """Startup config validation — incompatible flags and unsafe production combos."""

    def validate(self, registry: NewsroomConfigRegistry) -> ConfigValidationReport:
        cfg = registry.to_dict()
        issues: list[ConfigValidationIssue] = []
        incompatible: list[str] = []

        def add(sev: str, code: str, msg: str, fix: str) -> None:
            issues.append(ConfigValidationIssue(sev, code, msg, fix))

        env = cfg.get("APP_ENV", "development")
        is_prod = env == "production"

        if cfg.get("OPS_CHAOS_ENABLED", "false").lower() in ("1", "true", "yes") and is_prod:
            add(
                "error",
                "chaos_in_production",
                "OPS_CHAOS_ENABLED must not be true in production",
                "Set OPS_CHAOS_ENABLED=false",
            )
            incompatible.append("OPS_CHAOS_ENABLED+production")

        if (
            cfg.get("RECOVERY_MODE", "false").lower() in ("1", "true", "yes")
            and not cfg.get("DEGRADED_STARTUP", "false").lower() in ("1", "true", "yes")
            and is_prod
        ):
            add(
                "warn",
                "recovery_without_degraded",
                "RECOVERY_MODE in production without DEGRADED_STARTUP",
                "Set DEGRADED_STARTUP=true or disable RECOVERY_MODE after verify",
            )

        if cfg.get("NEWSROOM_DUAL_WRITE", "false").lower() in ("1", "true", "yes"):
            if cfg.get("NEWSROOM_USE_POSTGRES", "false").lower() not in ("1", "true", "yes"):
                add(
                    "error",
                    "dual_write_without_postgres",
                    "NEWSROOM_DUAL_WRITE requires NEWSROOM_USE_POSTGRES",
                    "Enable Postgres or disable dual write",
                )
                incompatible.append("DUAL_WRITE+no_postgres")

        rollout = cfg.get("PRODUCTION_ROLLOUT_STAGE", "INTERNAL_SHADOW")
        publish_mode = cfg.get("RELIABILITY_PUBLISH_MODE", "SHADOW")
        if rollout in ("NORMAL_PRODUCTION", "HIGH_VOLUME_PRODUCTION") and publish_mode == "SHADOW":
            add(
                "warn",
                "rollout_publish_mismatch",
                f"Rollout {rollout} with RELIABILITY_PUBLISH_MODE=SHADOW",
                "Align publish mode before public activation",
            )

        if cfg.get("SHADOW_PUBLISH_ONLY", "false").lower() in ("1", "true", "yes"):
            if rollout not in ("INTERNAL_SHADOW",):
                add(
                    "error",
                    "shadow_flag_public_rollout",
                    "SHADOW_PUBLISH_ONLY conflicts with public rollout stage",
                    "Clear SHADOW_PUBLISH_ONLY or rollback rollout",
                )
                incompatible.append("SHADOW_PUBLISH_ONLY+public_rollout")

        if is_prod and cfg.get("STREAM_BACKEND", "inmemory") == "inmemory":
            add(
                "warn",
                "inmemory_stream_production",
                "In-memory stream bus in production",
                "Set STREAM_BACKEND=redis_streams for multi-node",
            )

        errors = [i for i in issues if i.severity == "error"]
        return ConfigValidationReport(
            passed=len(errors) == 0,
            fingerprint=registry.fingerprint(),
            issues=tuple(issues),
            incompatible_pairs=tuple(incompatible),
        )

    def diff(
        self,
        current: NewsroomConfigRegistry,
        stored: dict[str, Any] | None,
    ) -> list[str]:
        if stored is None:
            return ["No stored fingerprint — run startup to baseline"]
        prev = stored.get("config", {})
        cur = current.to_dict()
        changes: list[str] = []
        for key in sorted(set(prev) | set(cur)):
            if prev.get(key) != cur.get(key):
                changes.append(f"{key}: {prev.get(key)!r} → {cur.get(key)!r}")
        return changes
