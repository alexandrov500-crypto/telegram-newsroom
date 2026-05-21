"""Evolution safety gates before accepting config/policy/ranking changes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

logger = __import__("logging").getLogger(__name__)

CHANGE_TYPES = frozenset({
    "config",
    "policy",
    "ranking_weights",
    "profile",
    "migration",
    "economic_mode",
    "operational_mode",
})


def validate_evolution_change(
    settings: Any,
    *,
    change_type: str,
    payload: dict[str, Any] | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """
    Dry-run validation: schema, replay regression threshold, policy JSON validity.
    Returns {ok, fatal, warnings, checks}.
    """
    fatal: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, Any]] = []
    ct = str(change_type or "").strip().lower()
    if ct not in CHANGE_TYPES:
        fatal.append(f"unknown_change_type:{ct}")

    rd = settings.runtime_state_dir
    pl = payload or {}

    if ct == "policy":
        rules = pl.get("rules") if "rules" in pl else pl
        if rules is not None:
            try:
                json.dumps(rules)
                if not isinstance(rules, list):
                    fatal.append("policy_rules_must_be_list")
            except (TypeError, ValueError) as exc:
                fatal.append(f"policy_invalid_json:{exc}")

    if ct == "ranking_weights":
        w = pl.get("weights") if isinstance(pl.get("weights"), dict) else pl
        if not isinstance(w, dict):
            fatal.append("ranking_weights_must_be_object")
        else:
            for k, v in w.items():
                try:
                    fv = float(v)
                    if fv < -1.0 or fv > 2.0:
                        warnings.append(f"weight_out_of_typical_range:{k}")
                except (TypeError, ValueError):
                    fatal.append(f"invalid_weight:{k}")

    if ct == "migration":
        from app.versioning import RUNTIME_STATE_SCHEMA_VERSION

        target = int(pl.get("target_schema_version") or RUNTIME_STATE_SCHEMA_VERSION)
        if target > RUNTIME_STATE_SCHEMA_VERSION:
            fatal.append("migration_target_newer_than_runtime")

    if ct in ("config", "profile"):
        fp = pl.get("config_fingerprint") or pl.get("fingerprint")
        if fp and len(str(fp)) < 8:
            warnings.append("weak_config_fingerprint")

    # Schema validation on governance files
    for rel in ("editorial/governance_rules.json", "editorial/ranking_weights.json"):
        p = Path(rd) / rel
        if p.is_file():
            try:
                json.loads(p.read_text(encoding="utf-8"))
                checks.append({"check": "schema_json", "path": rel, "ok": True})
            except (OSError, json.JSONDecodeError) as exc:
                fatal.append(f"invalid_json:{rel}:{exc}")

    # Regression threshold (offline replay snapshot compare)
    if not fatal:
        from ops.trust.behavior_regression import run_behavior_regression

        reg = run_behavior_regression(rd, window_hours=float(os.getenv("EVOLUTION_REGRESSION_WINDOW_HOURS", "24")))
        checks.append({"check": "behavior_regression", "passed": reg.get("passed"), "diff_count": reg.get("diff_count")})
        if not reg.get("passed"):
            fatal.append(f"regression_threshold_exceeded:diffs={reg.get('diff_count')}")

    ok = not fatal
    result = {
        "ok": ok,
        "dry_run": dry_run,
        "change_type": ct,
        "fatal": fatal,
        "warnings": warnings,
        "checks": checks,
    }
    if not ok:
        log_event(
            logger,
            "runtime.evolution.validation.failed",
            change_type=ct,
            fatal=fatal,
            warnings=warnings,
        )
    return result
