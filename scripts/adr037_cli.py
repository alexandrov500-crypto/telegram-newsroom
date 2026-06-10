#!/usr/bin/env python3
"""ADR-037 unified operator CLI — routing-only entrypoint (no business logic).

Views/transformers over computed state — not a source of truth.
Maps run modes to existing orchestrators. Does not mutate production guardrails.
See docs/adr037-final-operational-form.md for operational closure.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

MODES = frozenset({"observe", "diagnose", "heal", "stabilize", "govern", "evolve", "simulate"})

MUTATING_MODES = frozenset({"heal", "stabilize", "evolve"})
READ_ONLY_MODES = frozenset({"observe", "diagnose", "govern", "simulate"})


@dataclass
class RunOptions:
    json_output: bool = False
    dry_run: bool = False
    force: bool = False
    notify: bool = False
    incident_id: str | None = None
    skip_pr: bool = False
    no_persist: bool = False
    proposal_id: str | None = None


def _print_or_json(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    elif isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {value}")
    else:
        print(payload)


def build_status_snapshot() -> dict[str, Any]:
    from scripts.registry_adapters import load_unified_state

    return load_unified_state().to_snapshot()


def run_observe(opts: RunOptions) -> dict[str, Any]:
    from scripts.event_rules_engine import apply_rules
    from scripts.migration_observability_common import (
        build_event_stream,
        persist_new_events,
        write_gate_status_snapshot,
    )

    events = build_event_stream()
    if not opts.dry_run:
        persist_new_events(events)
        events = build_event_stream()

    dry_rules = opts.dry_run
    notifications = apply_rules(dry_run=dry_rules)

    if not opts.dry_run:
        write_gate_status_snapshot()

    snapshot = build_status_snapshot()
    return {
        "mode": "observe",
        "dry_run": opts.dry_run,
        "snapshot": snapshot,
        "event_count": len(events),
        "recent_events": [e.to_dict() for e in events[-10:]],
        "notifications": [
            {"channel": n.channel, "severity": n.severity, "event_type": n.event_type}
            for n in notifications
        ],
        "production_mutated": not opts.dry_run,
    }


def run_diagnose(opts: RunOptions) -> dict[str, Any]:
    from scripts.agents.adversarial_orchestrator import run_adversarial_pipeline
    from scripts.agents.multi_agent_orchestrator import run_multi_agent_pipeline
    from scripts.failure_analyzer import analyze
    from scripts.remediation_planner import build_plan

    snapshot = build_status_snapshot()
    incident_id = opts.incident_id
    if not incident_id and snapshot.get("open_incident_ids"):
        incident_id = snapshot["open_incident_ids"][-1]

    analysis = analyze(incident_id=incident_id)
    plan = build_plan(analysis)
    ma_trace = run_multi_agent_pipeline(
        incident_id=incident_id,
        analysis=analysis,
        plan=plan,
        trigger="adr037_cli_diagnose",
    )
    adversarial = run_adversarial_pipeline(
        incident_id=incident_id,
        persist=not opts.no_persist and not opts.dry_run,
    )

    return {
        "mode": "diagnose",
        "read_only": opts.no_persist or opts.dry_run,
        "snapshot": snapshot,
        "incident_id": incident_id,
        "analysis": analysis.to_dict(),
        "multi_agent": ma_trace,
        "adversarial_summary": adversarial.get("summary"),
        "adversarial_report_id": adversarial.get("report_id"),
        "production_mutated": not opts.no_persist and not opts.dry_run,
    }


def run_heal(opts: RunOptions) -> dict[str, Any]:
    from scripts.auto_healing_orchestrator import run_pipeline

    if opts.dry_run:
        return {
            "mode": "heal",
            "skipped": True,
            "reason": "dry_run — healing not executed",
            "production_mutated": False,
        }

    result = run_pipeline(
        incident_id=opts.incident_id,
        dry_run=False,
        skip_pr=opts.skip_pr,
        notify=opts.notify,
        force=opts.force,
    )
    result["mode"] = "heal"
    return result


def run_stabilize(opts: RunOptions) -> dict[str, Any]:
    from scripts.stabilization_loop_orchestrator import run_loop

    if opts.dry_run:
        return {
            "mode": "stabilize",
            "skipped": True,
            "reason": "dry_run — stabilization not executed",
            "production_mutated": False,
        }

    result = run_loop(
        incident_id=opts.incident_id,
        dry_run=False,
        skip_pr=opts.skip_pr,
        notify=opts.notify,
        force=opts.force,
    )
    result["mode"] = "stabilize"
    return result


def run_govern(opts: RunOptions) -> dict[str, Any]:
    from scripts.governance.governance_orchestrator import run_governance
    from scripts.governance.policy_drift_detector import detect_drift
    from scripts.governance.reliability_metrics_engine import compute_metrics

    metrics = compute_metrics()
    drift = detect_drift()
    orchestration = run_governance(dry_run=True, skip_pr=True)

    return {
        "mode": "govern",
        "snapshot": build_status_snapshot(),
        "health_score": metrics.get("system_health_score"),
        "drift": drift.to_dict(),
        "metrics_summary": {
            "mttr_trend": metrics.get("trends", {}).get("mttr"),
            "stabilization_success": metrics.get("stabilization", {}).get("success_rate"),
            "adversarial_coverage": metrics.get("adversarial_detection_coverage"),
        },
        "orchestration": orchestration,
        "production_mutated": False,
    }


def run_evolve(opts: RunOptions) -> dict[str, Any]:
    from scripts.evolution.evolution_orchestrator import run_evolution_loop

    result = run_evolution_loop(
        proposal_id=opts.proposal_id,
        dry_run=True,
        skip_apply=True,
    )
    result["mode"] = "evolve"
    result["apply_skipped"] = True
    return result


def run_simulate(opts: RunOptions) -> dict[str, Any]:
    return {
        "mode": "simulate",
        "status": "not_implemented",
        "message": "What-if shadow runtime reserved for future ADR-037 extension",
        "snapshot": build_status_snapshot(),
        "hint": "Use 'evolve' for regression-gated proposals or 'diagnose' for adversarial replay",
        "production_mutated": False,
    }


MODE_HANDLERS: dict[str, Callable[[RunOptions], dict[str, Any]]] = {
    "observe": run_observe,
    "diagnose": run_diagnose,
    "heal": run_heal,
    "stabilize": run_stabilize,
    "govern": run_govern,
    "evolve": run_evolve,
    "simulate": run_simulate,
}


def run_mode(mode: str, opts: RunOptions) -> tuple[dict[str, Any], int]:
    mode = mode.lower().strip()
    if mode not in MODES:
        raise ValueError(f"Unknown mode: {mode}")

    if mode in READ_ONLY_MODES and opts.force and mode != "govern":
        pass  # force only affects heal/stabilize triggers

    handler = MODE_HANDLERS[mode]
    result = handler(opts)
    exit_code = _exit_code_for_result(mode, result)
    return result, exit_code


def _exit_code_for_result(mode: str, result: dict[str, Any]) -> int:
    if result.get("skipped") and mode in {"heal", "stabilize"}:
        return 0

    if mode == "diagnose":
        adv = result.get("adversarial_summary") or {}
        if adv.get("highest_severity") == "CRITICAL":
            return 2
        ma = result.get("multi_agent") or {}
        if ma.get("final_decision") in {"STOP_THE_LINE", "BLOCK"}:
            return 2

    if mode == "govern":
        drift = result.get("drift") or {}
        if drift.get("severity") == "CRITICAL":
            return 2

    if mode == "evolve":
        evaluations = result.get("evaluations") or []
        if any((e.get("decision") or {}).get("action") == "BLOCK" for e in evaluations):
            return 1

    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adr037",
        description="ADR-037 distributed reliability runtime — single operator entrypoint",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    status_p = sub.add_parser("status", help="Quick phase / gate / risk / incident snapshot")
    status_p.add_argument("--json", action="store_true", help="JSON output")

    state_p = sub.add_parser("state", help="Full unified logical state (policy + events + trace)")
    state_p.add_argument("--json", action="store_true", help="JSON output")

    run_p = sub.add_parser("run", help="Execute an ADR-037 mode")
    run_p.add_argument(
        "mode",
        choices=sorted(MODES),
        help="observe|diagnose|heal|stabilize|govern|evolve|simulate",
    )
    run_p.add_argument("--json", action="store_true", help="JSON output")
    run_p.add_argument("--dry-run", action="store_true", help="No writes / no side effects where supported")
    run_p.add_argument("--force", action="store_true", help="Force heal/stabilize even without trigger")
    run_p.add_argument("--notify", action="store_true", help="Send Telegram notifications (heal/stabilize)")
    run_p.add_argument("--incident-id", help="Target incident for diagnose/heal/stabilize")
    run_p.add_argument("--skip-pr", action="store_true", help="Skip draft PR generation (heal/stabilize)")
    run_p.add_argument("--no-persist", action="store_true", help="Diagnose: skip adversarial report files")
    run_p.add_argument("--proposal-id", help="Evolve: specific RES-xxx proposal")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "status":
        snapshot = build_status_snapshot()
        if getattr(args, "json", False):
            print(json.dumps(snapshot, indent=2, ensure_ascii=False))
        else:
            print(f"phase={snapshot['phase']} gate={snapshot['gate'].get('status')}")
            print(f"incidents={snapshot['active_incidents']} critical_risks={snapshot['critical_risks']}")
            if snapshot.get("stop_the_line"):
                print("STOP-THE-LINE: active CRITICAL risk(s)")
            print("allowed:", ", ".join(snapshot.get("allowed_actions") or []))
        return 2 if snapshot.get("stop_the_line") else 0

    if args.command == "state":
        from scripts.registry_adapters import load_unified_state

        state = load_unified_state()
        payload = state.to_dict()
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        else:
            snap = payload["snapshot"]
            print(f"phase={snap['phase']} unified_state={snap.get('unified_state')}")
            print(f"policy_changes={snap.get('policy_change_count')} pending_evolution={snap.get('pending_evolution')}")
            print(f"trace_sources={payload['decision_trace'].get('source_files')}")
        return 2 if state.stop_the_line() else 0

    opts = RunOptions(
        json_output=args.json,
        dry_run=args.dry_run,
        force=args.force,
        notify=args.notify,
        incident_id=args.incident_id,
        skip_pr=args.skip_pr,
        no_persist=args.no_persist,
        proposal_id=args.proposal_id,
    )

    try:
        result, exit_code = run_mode(args.mode, opts)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    _print_or_json(result, as_json=opts.json_output)
    if not opts.json_output and result.get("production_mutated") is False:
        print("(production guardrails unchanged)")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
