"""Deterministic long-running soak harness (CI-safe bounded mode)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from utils.resource_stability import ResourceSnapshot, analyze_memory_trend, snapshot_resources
from utils.reliability_diagnostics import build_stability_evidence, write_stability_evidence


@dataclass
class SoakCycleResult:
    name: str
    ok: bool
    duration_sec: float
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class SoakHarnessResult:
    cycles: list[SoakCycleResult] = field(default_factory=list)
    resource_samples: list[ResourceSnapshot] = field(default_factory=list)
    artifacts: dict[str, Path] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.cycles)


class SoakHarness:
    """Bounded soak runner for CI and local extended mode."""

    def __init__(self, *, work_dir: Path, extended: bool = False) -> None:
        self.work_dir = work_dir.expanduser().resolve()
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.extended = extended
        self.default_cycles = 24 if extended else 6

    def run_cycles(
        self,
        specs: list[tuple[str, Callable[[], None]]],
        *,
        resource_sample_every: int = 2,
    ) -> SoakHarnessResult:
        out = SoakHarnessResult()
        for idx, (name, fn) in enumerate(specs):
            t0 = time.perf_counter()
            ok = True
            detail: dict[str, Any] = {}
            try:
                fn()
            except Exception as exc:
                ok = False
                detail["error"] = repr(exc)
            dur = time.perf_counter() - t0
            out.cycles.append(
                SoakCycleResult(name=name, ok=ok, duration_sec=round(dur, 4), detail=detail)
            )
            if resource_sample_every > 0 and idx % resource_sample_every == 0:
                out.resource_samples.append(snapshot_resources())
        return out

    async def run_async_cycles(
        self,
        specs: list[tuple[str, Callable[[], Any]]],
        *,
        resource_sample_every: int = 2,
    ) -> SoakHarnessResult:
        out = SoakHarnessResult()

        async def _one(name: str, fn: Callable[[], Any]) -> SoakCycleResult:
            t0 = time.perf_counter()
            try:
                res = fn()
                if asyncio.iscoroutine(res):
                    await res
                return SoakCycleResult(
                    name=name, ok=True, duration_sec=round(time.perf_counter() - t0, 4)
                )
            except Exception as exc:
                return SoakCycleResult(
                    name=name,
                    ok=False,
                    duration_sec=round(time.perf_counter() - t0, 4),
                    detail={"error": repr(exc)},
                )

        for idx, (name, fn) in enumerate(specs):
            out.cycles.append(await _one(name, fn))
            if resource_sample_every > 0 and idx % resource_sample_every == 0:
                out.resource_samples.append(snapshot_resources())
        return out

    def write_artifacts(
        self, result: SoakHarnessResult, *, wal_bytes: int = 0, retry_count: int = 0
    ) -> None:
        mem = analyze_memory_trend(result.resource_samples)
        payload = {
            "schema_version": 1,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "extended": self.extended,
            "cycles": [
                {"name": c.name, "ok": c.ok, "duration_sec": c.duration_sec, "detail": c.detail}
                for c in result.cycles
            ],
            "memory_trend": mem,
            "stability": build_stability_evidence(
                retry_count=retry_count,
                wal_bytes=wal_bytes,
                trace_count=len(result.resource_samples),
            ),
        }
        p = self.work_dir / "soak_harness_report.json"
        p.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result.artifacts["soak_harness_report"] = p
        write_stability_evidence(self.work_dir / "stability_evidence.json", payload["stability"])


def simulate_wal_churn(db_path: Path, *, inserts: int = 40) -> int:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS soak_churn (id INTEGER PRIMARY KEY, v TEXT)")
    for i in range(inserts):
        conn.execute("INSERT INTO soak_churn (v) VALUES (?)", (f"v{i}",))
    conn.commit()
    conn.close()
    wal = Path(f"{db_path}-wal")
    return int(wal.stat().st_size) if wal.is_file() else 0


def simulate_snapshot_restore_cycle(output_dir: Path, source_runtime: Path) -> bool:
    import shutil

    od = output_dir.expanduser().resolve()
    od.mkdir(parents=True, exist_ok=True)
    if (od / "runtime").exists():
        shutil.rmtree(od / "runtime")
    shutil.copytree(source_runtime, od / "runtime")
    return (od / "runtime" / "runtime_index.json").is_file()
