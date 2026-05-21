"""Cost-aware AI budget controls (hourly windows, priority-aware)."""

from __future__ import annotations

import os
import time
from typing import Any

from editorial.intelligence_store import load_json, save_json
from ops.economics.paths import budget_state_path


def _limits() -> dict[str, int]:
    return {
        "max_tokens_per_hour": int(os.getenv("AI_MAX_TOKENS_PER_HOUR", "120000")),
        "max_requests_per_hour": int(os.getenv("AI_MAX_REQUESTS_PER_HOUR", "60")),
        "cooldown_sec": int(os.getenv("AI_COOLDOWN_SEC", "0")),
    }


def _hour_window() -> str:
    return time.strftime("%Y-%m-%dT%H", time.gmtime())


def _load(runtime_dir: str) -> dict[str, Any]:
    return load_json(
        budget_state_path(runtime_dir),
        {"version": 1, "hour": "", "tokens": 0, "requests": 0, "cooldown_until": 0.0, "ai_cooldown_mode": False},
    )


def _save(runtime_dir: str, data: dict[str, Any]) -> None:
    save_json(budget_state_path(runtime_dir), data)


def record_ai_usage(
    runtime_dir: str,
    *,
    tokens: int = 0,
    requests: int = 1,
    cost_usd: float = 0.0,
) -> None:
    data = _load(runtime_dir)
    hk = _hour_window()
    if data.get("hour") != hk:
        data = {"version": 1, "hour": hk, "tokens": 0, "requests": 0, "cooldown_until": 0.0, "ai_cooldown_mode": False}
    data["tokens"] = int(data.get("tokens") or 0) + max(0, tokens)
    data["requests"] = int(data.get("requests") or 0) + max(0, requests)
    data["last_cost_usd"] = round(float(data.get("last_cost_usd") or 0) + cost_usd, 8)
    _save(runtime_dir, data)
    from ops.economics.resource_accounting import record_resource

    record_resource(runtime_dir, stage="openai", tokens=tokens, cost_usd=cost_usd, count=requests)


def set_ai_cooldown(runtime_dir: str, *, sec: float, reason: str = "") -> None:
    data = _load(runtime_dir)
    data["cooldown_until"] = time.time() + max(1.0, sec)
    data["ai_cooldown_mode"] = True
    data["cooldown_reason"] = reason[:200]
    _save(runtime_dir, data)


def budget_pressure(runtime_dir: str) -> float:
    """0..1 pressure on hourly AI budget."""
    lim = _limits()
    data = _load(runtime_dir)
    if data.get("hour") != _hour_window():
        return 0.0
    tok_p = int(data.get("tokens") or 0) / max(1, lim["max_tokens_per_hour"])
    req_p = int(data.get("requests") or 0) / max(1, lim["max_requests_per_hour"])
    return round(min(1.0, max(tok_p, req_p)), 4)


def allow_ai_request(
    runtime_dir: str,
    *,
    priority_level: str = "medium",
    economic_mode: str = "balanced",
) -> tuple[bool, str]:
    """
    Priority-aware AI gate. High priority retains access under pressure.
    Returns (allowed, reason).
    """
    lim = _limits()
    data = _load(runtime_dir)
    now = time.time()
    if float(data.get("cooldown_until") or 0) > now:
        return False, "ai_cooldown_active"
    hk = _hour_window()
    if data.get("hour") != hk:
        data = {"version": 1, "hour": hk, "tokens": 0, "requests": 0}
    tokens = int(data.get("tokens") or 0)
    requests = int(data.get("requests") or 0)
    pressure = budget_pressure(runtime_dir)
    pri = str(priority_level or "medium").lower()
    high = pri in ("high", "breaking", "critical")
    if economic_mode == "low_cost" and not high:
        return False, "economic_mode_low_cost"
    if economic_mode == "crisis_mode" and not high:
        return False, "economic_mode_crisis"
    if tokens >= lim["max_tokens_per_hour"]:
        if high and pressure < 1.15:
            return True, "priority_override_tokens"
        return False, "token_budget_exhausted"
    if requests >= lim["max_requests_per_hour"]:
        if high and requests < lim["max_requests_per_hour"] + 3:
            return True, "priority_override_requests"
        return False, "request_budget_exhausted"
    if pressure >= 0.85 and pri == "low":
        return False, "budget_pressure_low_priority"
    if pressure >= 0.95 and pri == "medium":
        return False, "budget_pressure_medium_priority"
    return True, "ok"


def budgets_payload(runtime_dir: str) -> dict[str, Any]:
    from ops.economics.economic_mode import load_economic_mode

    data = _load(runtime_dir)
    lim = _limits()
    pressure = budget_pressure(runtime_dir)
    mode = load_economic_mode(runtime_dir)
    return {
        "limits": lim,
        "hour_window": _hour_window(),
        "usage": {
            "tokens": int(data.get("tokens") or 0),
            "requests": int(data.get("requests") or 0),
            "last_cost_usd": data.get("last_cost_usd"),
        },
        "pressure": pressure,
        "ai_cooldown_mode": bool(data.get("ai_cooldown_mode")) or float(data.get("cooldown_until") or 0) > time.time(),
        "adaptive_degradation": pressure >= 0.7,
        "economic_mode": mode.value,
        "fallback_summarize": "lexical_digest" if pressure >= 0.9 else "full",
    }
