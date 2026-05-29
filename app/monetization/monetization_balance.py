"""Editorial monetization balance — prevent quality dilution."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MonetizationBalanceVerdict:
    allowed: bool
    stress_score: float
    sponsor_ratio_24h: float
    editorial_ratio_24h: float
    reason: str


def _log_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "monetization_publish_log.json"


def record_publish_type(runtime_dir: str, publish_type: str) -> None:
    p = _log_path(runtime_dir)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"events": []}
    events = list(data.get("events") or [])
    events.insert(0, {"type": publish_type, "ts": time.time()})
    data["events"] = events[:500]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


def evaluate_monetization_stress(runtime_dir: str) -> MonetizationBalanceVerdict:
    if os.getenv("W5_MONETIZATION_BALANCE_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return MonetizationBalanceVerdict(True, 0.0, 0.0, 1.0, "disabled")

    try:
        data = json.loads(_log_path(runtime_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return MonetizationBalanceVerdict(True, 0.0, 0.0, 1.0, "no_history")

    now = time.time()
    recent = [e for e in (data.get("events") or []) if now - float(e.get("ts") or 0) < 86400]
    if not recent:
        return MonetizationBalanceVerdict(True, 0.0, 0.0, 1.0, "no_recent")

    sponsored = sum(1 for e in recent if e.get("type") == "sponsored")
    editorial = sum(1 for e in recent if e.get("type") != "sponsored")
    total = sponsored + editorial or 1
    sponsor_ratio = sponsored / total
    editorial_ratio = editorial / total

    max_ratio = float(os.getenv("W5_MAX_SPONSOR_RATIO_24H", "0.18"))
    stress = round(sponsor_ratio / max_ratio if max_ratio > 0 else 0.0, 4)

    if sponsor_ratio > max_ratio:
        return MonetizationBalanceVerdict(
            False,
            stress,
            round(sponsor_ratio, 4),
            round(editorial_ratio, 4),
            "sponsor_overload",
        )

    return MonetizationBalanceVerdict(
        True,
        stress,
        round(sponsor_ratio, 4),
        round(editorial_ratio, 4),
        "ok",
    )


def can_inject_sponsor(runtime_dir: str) -> bool:
    v = evaluate_monetization_stress(runtime_dir)
    return v.allowed and v.stress_score < 0.95
