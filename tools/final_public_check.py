#!/usr/bin/env python3
"""Final public pre-launch integration check."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    return p.returncode, (p.stdout + "\n" + p.stderr).strip()


def _build_contract_report(*, test_mode_final_gate: bool) -> dict[str, object]:
    from app.testing.e2e_pipeline_validator import run_e2e_validation, write_e2e_validation_report
    from app.testing.telegram_live_simulation import simulate_telegram_live_flow, write_telegram_simulation_report
    from app.observability.final_stability_report import build_final_stability_report, write_final_stability_report
    from app.observability.validation_contract import evaluate_release_contract, evaluate_required_only_contract, metric
    from app.observability.validation_environment import detect_validation_environment, observational_policy
    from app.observability.release_contract import REQUIRED_CONTRACT_FIELDS, OBSERVATIONAL_CONTRACT_FIELDS

    runtime_dir = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    runtime_dir.mkdir(parents=True, exist_ok=True)

    e2e = run_e2e_validation()
    write_e2e_validation_report(e2e)
    sim = simulate_telegram_live_flow()
    write_telegram_simulation_report(str(runtime_dir), sim)
    fs = build_final_stability_report(str(runtime_dir))
    write_final_stability_report(str(runtime_dir), fs)
    rc, out = _run([sys.executable, "tools/public_go_check.py", "--json"])
    go: dict[str, object] = {}
    try:
        go = json.loads(out.splitlines()[0] if out.strip().startswith("{") else out)
    except Exception:
        go = {"parse_error": out[:500]}

    fs_required = {
        str(m.get("name")): m
        for m in (fs.get("required_checks") or [])
        if isinstance(m, dict) and str(m.get("name") or "")
    }
    fs_observational = {
        str(m.get("name")): m
        for m in (fs.get("observational_checks") or [])
        if isinstance(m, dict) and str(m.get("name") or "")
    }

    required_checks: list[dict[str, str]] = []
    observational_checks: list[dict[str, str]] = []

    for name in sorted(REQUIRED_CONTRACT_FIELDS):
        item = fs_required.get(name)
        if item:
            required_checks.append(
                metric(name, str(item.get("state") or "UNKNOWN"), reason=str(item.get("reason") or ""))
            )
        else:
            required_checks.append(metric(name, "UNKNOWN", reason="required_field_missing_from_final_stability"))

    for name in sorted(OBSERVATIONAL_CONTRACT_FIELDS):
        item = fs_observational.get(name)
        if item:
            observational_checks.append(
                metric(name, str(item.get("state") or "UNKNOWN"), reason=str(item.get("reason") or ""), kind="observational")
            )
        else:
            observational_checks.append(metric(name, "UNKNOWN", reason="observational_field_missing", kind="observational"))

    if isinstance(go, dict):
        for b in go.get("blockers") or []:
            s = str(b)
            if "execution_graph" in s or "critical" in s or "rollback" in s or "duplicate" in s:
                for idx, m in enumerate(required_checks):
                    if m.get("name") == "execution_graph_verdict":
                        required_checks[idx] = metric(
                            "execution_graph_verdict", "FAIL", reason=f"public_go:{s}"
                        )
                        break
            elif "latency" in s:
                for idx, m in enumerate(observational_checks):
                    if m.get("name") == "latency_metrics":
                        observational_checks[idx] = metric(
                            "latency_metrics", "FAIL", reason=f"public_go:{s}", kind="observational"
                        )
                        break

    env_mode = detect_validation_environment()
    policy = observational_policy(env_mode)

    if test_mode_final_gate:
        contract = evaluate_required_only_contract(required=required_checks)
        release_verdict = str(contract.get("verdict") or "NOT_READY")
        warnings: list[str] = []
        for obs in observational_checks:
            st = str(obs.get("state") or "UNKNOWN")
            if st in {"FAIL", "UNKNOWN"}:
                warnings.append(f"observational_non_blocking:{obs.get('name')}:{st}")
    else:
        contract = evaluate_release_contract(
            source="final_public_check",
            required=required_checks,
            observational=observational_checks,
            ignore_missing_observational=bool(policy.get("ignore_missing_observational")),
        )
        release_verdict = str(contract.get("verdict") or "NOT_READY")
        warnings = list(contract.get("warnings") or [])

    if release_verdict == "READY_FOR_PUBLIC":
        verdict = "PASS"
    elif release_verdict == "CONDITIONAL":
        verdict = "WARN"
    else:
        verdict = "FAIL"

    return {
        "RELEASE_CONTRACT_VERDICT": release_verdict,
        "FINAL_PUBLIC_CHECK": verdict,
        "blockers": sorted(set(contract.get("blockers") or [])),
        "warnings": sorted(set(warnings)),
        "validation_environment": env_mode,
        "test_mode_final_gate": test_mode_final_gate,
        "required_checks": required_checks,
        "observational_checks": observational_checks,
        "determinism_key": {
            "required_states": {m["name"]: m["state"] for m in required_checks},
            "release_verdict": release_verdict,
        },
        "e2e_ok": bool(e2e.get("ok")),
        "telegram_sim_ok": bool(sim.get("ok")),
        "final_stability_verdict": str(fs.get("FINAL_STABILITY_VERDICT") or "NOT_READY"),
        "public_go_exit_code": rc,
        "runtime_dir": str(runtime_dir),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Final public pre-launch integration check")
    p.add_argument(
        "--test-mode-final-gate",
        action="store_true",
        help="Evaluate REQUIRED contract fields only (observational non-blocking)",
    )
    args = p.parse_args()

    report = _build_contract_report(test_mode_final_gate=bool(args.test_mode_final_gate))
    runtime_dir = Path(str(report.pop("runtime_dir")))
    out_path = runtime_dir / "final_public_check_report.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    verdict = str(report.get("FINAL_PUBLIC_CHECK") or "FAIL")
    return 0 if verdict == "PASS" else (2 if verdict == "WARN" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
