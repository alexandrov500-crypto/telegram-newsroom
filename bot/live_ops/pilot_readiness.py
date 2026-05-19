from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class PilotCheck:
    name: str
    passed: bool
    detail: str
    critical: bool = True


@dataclass
class PilotReadinessReport:
    ready: bool
    checks: list[PilotCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "detail": c.detail,
                    "critical": c.critical,
                }
                for c in self.checks
            ],
        }


def evaluate_pilot_env() -> PilotReadinessReport:
    report = PilotReadinessReport(ready=True)

    def add(name: str, ok: bool, detail: str, *, critical: bool = True) -> None:
        report.checks.append(PilotCheck(name, ok, detail, critical))
        if critical and not ok:
            report.ready = False

    enabled = os.getenv("CONTROLLED_LIVE_ENABLED", "").lower() in ("1", "true", "yes")
    if not enabled:
        enabled = os.getenv("LIVE_DEPLOY_ENABLED", "true").lower() not in ("0", "false", "no")
    add("controlled_live_enabled", enabled, "CONTROLLED_LIVE_ENABLED or LIVE_DEPLOY")

    mode = os.getenv("LIVE_MODE", "").lower()
    add("live_mode_canary", mode == "canary", f"LIVE_MODE={mode or 'unset'}")
    if mode == "autonomous_live":
        add("no_autonomous", False, "autonomous_live blocked during pilot", critical=True)

    max_h = os.getenv("LIVE_CANARY_MAX_PER_HOUR", "3")
    try:
        add(
            "canary_cap",
            int(max_h) <= 3,
            f"LIVE_CANARY_MAX_PER_HOUR={max_h} (pilot max 3)",
            critical=False,
        )
    except ValueError:
        add("canary_cap", False, f"invalid LIVE_CANARY_MAX_PER_HOUR={max_h}")

    pub = os.getenv("LIVE_PUBLIC_CHANNEL_ID") or os.getenv("TELEGRAM_CHANNEL_ID")
    add("public_channel", bool(pub and pub.startswith("-100")), f"public={pub or 'missing'}")

    ops = os.getenv("LIVE_OPS_CHANNEL_ID") or os.getenv("TELEGRAM_OPERATOR_CHAT_ID")
    add("ops_channel", bool(ops), f"ops={ops or 'missing'}")

    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    add("bot_token", bool(token), "BOT_TOKEN present")

    add(
        "supervised_approval",
        os.getenv("LIVE_SUPERVISED_APPROVAL", "true").lower() not in ("0", "false", "no"),
        "LIVE_SUPERVISED_APPROVAL",
        critical=False,
    )
    add(
        "freeze_on_anomaly",
        os.getenv("LIVE_FREEZE_ON_ANOMALY", "true").lower() not in ("0", "false", "no"),
        "LIVE_FREEZE_ON_ANOMALY",
        critical=False,
    )
    add(
        "rollback_enabled",
        os.getenv("LIVE_ENABLE_ROLLBACK", "true").lower() not in ("0", "false", "no"),
        "LIVE_ENABLE_ROLLBACK",
        critical=False,
    )

    shadow = os.getenv("SHADOW_PUBLISH_ONLY", "false").lower() in ("1", "true", "yes")
    add(
        "not_global_shadow",
        not shadow or mode == "shadow",
        f"SHADOW_PUBLISH_ONLY={shadow} (must be false for canary public pilot)",
    )

    return report


def evaluate_pilot_db(db_path: Path) -> PilotReadinessReport:
    report = PilotReadinessReport(ready=True)
    tables = (
        "live_publish_trace",
        "live_metrics_snapshots",
        "live_channel_incidents",
        "live_source_quarantine",
        "live_channel_state",
        "live_channel_publish_log",
    )

    try:
        conn = sqlite3.connect(db_path, timeout=5)
        for t in tables:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (t,),
            ).fetchone()
            ok = row is not None
            report.checks.append(PilotCheck(f"table_{t}", ok, "present" if ok else "missing"))
            if not ok:
                report.ready = False
        conn.close()
    except Exception as exc:
        report.checks.append(PilotCheck("db", False, str(exc)))
        report.ready = False
    return report


def persistence_snapshot(db_path: Path) -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        for table, key in (
            ("live_publish_trace", "trace_count"),
            ("live_metrics_snapshots", "metrics_count"),
            ("live_channel_incidents", "incidents_count"),
            ("live_source_quarantine", "quarantine_count"),
        ):
            try:
                row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                out[key] = int(row[0]) if row else 0
            except sqlite3.OperationalError:
                out[key] = -1
        conn.close()
    except Exception as exc:
        out["error"] = str(exc)
    return out
