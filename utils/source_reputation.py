from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_lock = threading.RLock()


def _runtime_dir(runtime_dir: str | None) -> Path:
    base = (runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).strip() or "var/runtime"
    p = Path(base).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _path(runtime_dir: str | None) -> Path:
    return _runtime_dir(runtime_dir) / "source_reputation.json"


def _load(runtime_dir: str | None) -> dict[str, Any]:
    path = _path(runtime_dir)
    if not path.is_file():
        return {"version": 1, "channels": {}}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": 1, "channels": {}}
    if not isinstance(data, dict):
        return {"version": 1, "channels": {}}
    ch = data.get("channels")
    if not isinstance(ch, dict):
        data["channels"] = {}
    data.setdefault("version", 1)
    return data


def _save(runtime_dir: str | None, data: dict[str, Any]) -> None:
    path = _path(runtime_dir)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _norm_channel(ch: str) -> str:
    return str(ch or "").strip().lower()


def _row_score(row: dict[str, Any]) -> float:
    pub = int(row.get("publishes") or 0)
    rej = int(row.get("rejects") or 0)
    dup = int(row.get("duplicate_signals") or 0)
    denom = max(1, pub + rej)
    approval_rate = pub / denom
    rejection_rate = rej / denom
    dup_rate = dup / max(1, pub + dup)
    score = 0.48 + 0.34 * approval_rate - 0.28 * rejection_rate - 0.18 * min(1.0, dup_rate)
    return round(max(0.06, min(0.97, score)), 3)


def export_channel_scores_for_priority(runtime_dir: str | None = None) -> dict[str, dict[str, Any]]:
    """Channel key (lower) -> {score, ...} for ``compute_editorial_priority``."""
    with _lock:
        data = _load(runtime_dir)
    out: dict[str, dict[str, Any]] = {}
    chans = data.get("channels")
    if not isinstance(chans, dict):
        return out
    for k, v in chans.items():
        if not isinstance(v, dict):
            continue
        key = _norm_channel(str(k))
        if not key:
            continue
        row = dict(v)
        row["score"] = _row_score(row)
        row["approval_rate"] = round(
            int(row.get("publishes") or 0) / max(1, int(row.get("publishes") or 0) + int(row.get("rejects") or 0)), 4
        )
        out[key] = row
    return out


def record_publish_for_channels(channels: list[str], *, runtime_dir: str | None = None) -> None:
    if not channels:
        return
    with _lock:
        data = _load(runtime_dir)
        chmap = data.setdefault("channels", {})
        assert isinstance(chmap, dict)
        for ch in channels:
            key = _norm_channel(ch)
            if not key:
                continue
            row = dict(chmap.get(key) or {})
            row["publishes"] = int(row.get("publishes") or 0) + 1
            chmap[key] = row
        _save(runtime_dir, data)


def record_reject_for_channels(channels: list[str], *, runtime_dir: str | None = None) -> None:
    if not channels:
        return
    with _lock:
        data = _load(runtime_dir)
        chmap = data.setdefault("channels", {})
        assert isinstance(chmap, dict)
        for ch in channels:
            key = _norm_channel(ch)
            if not key:
                continue
            row = dict(chmap.get(key) or {})
            row["rejects"] = int(row.get("rejects") or 0) + 1
            chmap[key] = row
        _save(runtime_dir, data)


def record_duplicate_signal_for_channels(channels: list[str], *, runtime_dir: str | None = None) -> None:
    if not channels:
        return
    with _lock:
        data = _load(runtime_dir)
        chmap = data.setdefault("channels", {})
        assert isinstance(chmap, dict)
        for ch in channels:
            key = _norm_channel(ch)
            if not key:
                continue
            row = dict(chmap.get(key) or {})
            row["duplicate_signals"] = int(row.get("duplicate_signals") or 0) + 1
            chmap[key] = row
        _save(runtime_dir, data)
