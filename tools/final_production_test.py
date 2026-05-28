#!/usr/bin/env python3
"""Run full pre-public production validation suite."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    runtime_dir = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    runtime_dir.mkdir(parents=True, exist_ok=True)

    from app.testing.final_e2e_production_test import (
        run_final_e2e_production_test,
        write_final_e2e_production_test_report,
    )
    from app.testing.telegram_safe_launch_simulation import (
        simulate_telegram_safe_launch,
        write_telegram_safe_simulation_report,
    )
    from app.observability.final_system_consistency_check import (
        build_system_consistency_report,
        write_system_consistency_report,
    )
    from app.observability.final_release_readiness import (
        build_final_release_readiness_report,
        write_final_release_readiness_report,
    )

    e2e = run_final_e2e_production_test()
    write_final_e2e_production_test_report(e2e, runtime_dir=str(runtime_dir))

    sim = simulate_telegram_safe_launch()
    write_telegram_safe_simulation_report(sim, runtime_dir=str(runtime_dir))

    consistency = build_system_consistency_report(str(runtime_dir))
    write_system_consistency_report(str(runtime_dir), consistency)

    proc = subprocess.run(
        [sys.executable, "tools/final_public_check.py"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    public_out = proc.stdout.strip() or proc.stderr.strip()

    readiness = build_final_release_readiness_report(str(runtime_dir))
    write_final_release_readiness_report(str(runtime_dir), readiness)

    blockers: list[str] = []
    if not bool(e2e.get("ok")):
        blockers.append("e2e_production_test_failed")
    if not bool(sim.get("ok")):
        blockers.append("telegram_safe_simulation_failed")
    if str(consistency.get("SYSTEM_CONSISTENCY_VERDICT")) == "INCONSISTENT":
        blockers.extend(list(consistency.get("blockers") or []))
    blockers.extend(list(readiness.get("blockers") or []))

    hard_markers = (
        "required_failed:",
        "required_unknown:",
        "duplicate_publish",
        "publish_finalize",
        "rollback",
        "execution_graph",
    )
    blockers = sorted(set(blockers))
    fail = bool(blockers) or proc.returncode == 1
    if proc.returncode == 1 and not any(any(m in b for m in hard_markers) for b in blockers):
        blockers.append("final_public_check_failed")

    summary = {
        "FINAL_PRODUCTION_TEST": "FAIL" if fail else ("WARN" if proc.returncode == 2 else "PASS"),
        "FINAL_RELEASE_READINESS_VERDICT": readiness.get("FINAL_RELEASE_READINESS_VERDICT"),
        "blockers": blockers[:32],
        "e2e_ok": bool(e2e.get("ok")),
        "telegram_safe_ok": bool(sim.get("ok")),
        "system_consistency": consistency.get("SYSTEM_CONSISTENCY_VERDICT"),
        "final_public_check_exit_code": proc.returncode,
        "final_public_check_output": public_out[:2000],
    }
    out = runtime_dir / "final_production_test_summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if fail else (2 if proc.returncode == 2 else 0)


if __name__ == "__main__":
    raise SystemExit(main())
