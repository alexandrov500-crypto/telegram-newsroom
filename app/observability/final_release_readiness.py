"""Aggregate final release readiness from production validation artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.release_contract import FinalVerdict


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def build_final_release_readiness_report(runtime_dir: str) -> dict[str, Any]:
    rd = Path(runtime_dir).expanduser().resolve()
    e2e = _read_json(rd / "final_e2e_production_test_report.json")
    sim = _read_json(rd / "telegram_safe_simulation_report.json")
    consistency = _read_json(rd / "system_consistency_report.json")
    public_check = _read_json(rd / "final_public_check_report.json")

    blockers: list[str] = []
    warnings: list[str] = []

    if not bool(e2e.get("ok")):
        blockers.append("e2e_production_test_failed")
    if not bool(sim.get("ok")):
        blockers.append("telegram_safe_simulation_failed")
    if str(consistency.get("SYSTEM_CONSISTENCY_VERDICT") or "") == "INCONSISTENT":
        blockers.extend(list(consistency.get("blockers") or []))
        blockers.append("system_inconsistent")

    contract_verdict = str(public_check.get("RELEASE_CONTRACT_VERDICT") or "NOT_READY")
    if contract_verdict == FinalVerdict.NOT_READY.value:
        blockers.extend(list(public_check.get("blockers") or []))
    elif contract_verdict == FinalVerdict.CONDITIONAL.value:
        warnings.extend(list(public_check.get("warnings") or []))

    for b in public_check.get("blockers") or []:
        if str(b).startswith("required_failed:") or str(b).startswith("required_unknown:"):
            if str(b) not in blockers:
                blockers.append(str(b))

    if blockers:
        verdict = FinalVerdict.NOT_READY.value
    elif warnings:
        verdict = FinalVerdict.CONDITIONAL.value
    else:
        verdict = FinalVerdict.READY_FOR_PUBLIC.value

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "FINAL_RELEASE_READINESS_VERDICT": verdict,
        "blockers": sorted(set(blockers))[:32],
        "warnings": sorted(set(warnings))[:32],
        "artifacts": {
            "final_e2e_production_test": bool(e2e.get("ok")),
            "telegram_safe_simulation": bool(sim.get("ok")),
            "system_consistency": consistency.get("SYSTEM_CONSISTENCY_VERDICT"),
            "final_public_check": public_check.get("RELEASE_CONTRACT_VERDICT"),
        },
        "e2e_report": e2e,
        "telegram_safe_simulation_report": sim,
        "system_consistency_report": consistency,
        "final_public_check_report": public_check,
    }


def write_final_release_readiness_report(runtime_dir: str, report: dict[str, Any]) -> Path:
    out = Path(runtime_dir).expanduser().resolve() / "final_release_readiness_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out
