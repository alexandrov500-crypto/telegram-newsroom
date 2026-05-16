"""Bounded scalability simulation helpers."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


def simulate_queue_burst_depth(*, bursts: int, cap: int) -> dict[str, int]:
    depth = 0
    peak = 0
    for _ in range(bursts):
        depth = min(cap, depth + max(1, cap // 10))
        peak = max(peak, depth)
        depth = max(0, depth - max(1, cap // 20))
    return {"final_depth": depth, "peak_depth": peak, "cap": cap}


def simulate_retry_amplification(*, events: int, window_sec: float, threshold: int) -> dict[str, object]:
    now = time.monotonic()
    times = [now - (i * (window_sec / max(1, events))) for i in range(events)]
    burst = sum(1 for t in times if now - t <= window_sec)
    return {"events": events, "burst_in_window": burst, "threshold": threshold, "saturated": burst >= threshold}


def simulate_wal_pressure(db_path: Path, *, rounds: int, inserts_per_round: int) -> dict[str, int]:
    if db_path.is_file():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS scale_sim (id INTEGER PRIMARY KEY, v TEXT)")
    for _ in range(rounds):
        for i in range(inserts_per_round):
            conn.execute("INSERT INTO scale_sim (v) VALUES (?)", (f"x{i}",))
        conn.commit()
    conn.close()
    wal = Path(f"{db_path}-wal")
    return {
        "wal_bytes": int(wal.stat().st_size) if wal.is_file() else 0,
        "db_bytes": int(db_path.stat().st_size),
    }


def simulate_evidence_growth(base: Path, *, files: int, bytes_each: int) -> dict[str, int]:
    rt = base / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    for i in range(files):
        (rt / f"synthetic_{i}.json").write_text("x" * bytes_each, encoding="utf-8")
    total = sum(p.stat().st_size for p in rt.glob("*.json"))
    return {"file_count": files, "total_bytes": total}


def simulate_restore_duration_estimate(file_count: int, *, bytes_per_file: int) -> float:
    """Heuristic seconds for copy-only restore (no network)."""
    total_mb = (file_count * bytes_per_file) / (1024 * 1024)
    return round(max(0.01, total_mb * 0.02), 4)
