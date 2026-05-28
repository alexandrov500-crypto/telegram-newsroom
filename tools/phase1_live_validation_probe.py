#!/usr/bin/env python3
"""Poll /health + logs markers during live Phase 1 validation (read-only)."""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LOG = REPO / "logs" / "local-run.log"
HEALTH = "http://127.0.0.1:8080/health"


def fetch_health() -> dict | None:
    try:
        with urllib.request.urlopen(HEALTH, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def main() -> int:
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 360
    interval = 15
    samples: list[dict] = []
    markers = {
        "collect_started": False,
        "collect_finished": False,
        "collect_timeout": False,
        "collect_stalled": False,
        "summarize_trace": False,
        "draft_created": False,
        "explicit_reject": False,
        "wrapper_exit_summarize": False,
    }
    t0 = time.time()
    print(f"phase1_probe: watching {duration}s every {interval}s")
    while time.time() - t0 < duration:
        h = fetch_health()
        snap = {"t": round(time.time() - t0, 1)}
        if h:
            tc = h.get("telegram_connectivity") or {}
            cc = tc.get("collect_cycle") or {}
            snap.update(
                {
                    "status": h.get("status"),
                    "async_integrity_ok": h.get("async_integrity_ok"),
                    "dc_reachable": tc.get("dc_reachable"),
                    "collect_in_progress": cc.get("collect_in_progress"),
                    "collect_stalled": cc.get("collect_stalled"),
                    "collect_elapsed": cc.get("collect_elapsed_sec"),
                    "polling_retry": tc.get("polling_retry_count"),
                    "conflict": tc.get("conflict_detected"),
                }
            )
            if cc.get("collect_stalled"):
                markers["collect_stalled"] = True
        else:
            snap["health"] = "down"
        samples.append(snap)
        print(json.dumps(snap, ensure_ascii=False))

        if LOG.exists():
            tail = LOG.read_text(encoding="utf-8", errors="replace")[-120000:]
            if "collect_cycle.started" in tail:
                markers["collect_started"] = True
            if "collect_cycle.finished" in tail:
                markers["collect_finished"] = True
            if "COLLECT_CYCLE_TIMEOUT" in tail:
                markers["collect_timeout"] = True
            if "COLLECT_CYCLE_STALLED" in tail:
                markers["collect_stalled"] = True
            if re.search(r"PIPELINE_EXECUTION_TRACE.*step.*summarize", tail):
                markers["summarize_trace"] = True
            if re.search(r"wrapper_exit.*summarize", tail):
                markers["wrapper_exit_summarize"] = True
            if re.search(r"draft_created|tick_draft_id|draft\.created", tail, re.I):
                markers["draft_created"] = True
            if re.search(r"explicit_reject|desk_reject|pipeline\.backlog_explicit_reject", tail):
                markers["explicit_reject"] = True

        if markers["collect_finished"] and (
            markers["draft_created"] or markers["explicit_reject"] or markers["wrapper_exit_summarize"]
        ):
            print("phase1_probe: tick outcome detected, stopping early")
            break
        time.sleep(interval)

    out = {"samples": samples, "markers": markers, "watched_sec": round(time.time() - t0, 1)}
    out_path = REPO / "var" / "runtime" / "phase1_live_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"written {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
