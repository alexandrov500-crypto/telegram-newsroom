"""Canary operational mode — shadow compare without production mutation."""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

from editorial.intelligence_store import load_json, save_json
from ops.trust.paths import canary_state_path


def is_canary_enabled() -> bool:
    return os.getenv("RUNTIME_CANARY_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _weights_hash(runtime_dir: str, *, canary: bool = False) -> str:
    from editorial.governance.paths import ranking_weights_path
    from pathlib import Path

    p = Path(runtime_dir) / "editorial" / ("ranking_weights_canary.json" if canary else "ranking_weights.json")
    if not p.is_file():
        return ""
    try:
        raw = p.read_bytes()
        return hashlib.sha256(raw).hexdigest()[:16]
    except OSError:
        return ""


def record_shadow_comparison(
    runtime_dir: str,
    *,
    live_ranked: list[dict[str, Any]],
    kind: str = "ranking",
) -> None:
    if not is_canary_enabled():
        return
    live_fps = [r.get("fingerprint") for r in live_ranked[:15]]
    live_hash = _weights_hash(runtime_dir, canary=False)
    shadow_hash = _weights_hash(runtime_dir, canary=True)
    weights_diverged = bool(shadow_hash) and shadow_hash != live_hash
    state = load_json(
        canary_state_path(runtime_dir),
        {"version": 1, "enabled": False, "comparisons": []},
    )
    state["enabled"] = True
    comp = {
        "kind": kind,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "weights_diverged": weights_diverged,
        "live_weights_hash": live_hash,
        "shadow_weights_hash": shadow_hash,
        "live_fingerprint_order": live_fps,
        "explainable": "shadow weights differ from live" if weights_diverged else "weights match",
    }
    comps = list(state.get("comparisons") or [])
    comps.insert(0, comp)
    state["comparisons"] = comps[:20]
    state["last_comparison_at"] = comp["ts"]
    save_json(canary_state_path(runtime_dir), state)


def canary_status_payload(runtime_dir: str) -> dict[str, Any]:
    state = load_json(canary_state_path(runtime_dir), {"comparisons": []})
    return {
        "enabled": is_canary_enabled(),
        "production_mutation": False,
        "shadow_capabilities": ["ranking_weights_diff", "governance_rules_canary.json"],
        "state": state,
    }
