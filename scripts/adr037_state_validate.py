#!/usr/bin/env python3
"""ADR-037 unified state validation — single CI gate on canonical state contract."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.migration_observability_common import (  # noqa: E402
    ADR037_OPERATIONAL_CLOSURE_DOC,
    ADR037_OPERATIONAL_CLOSURE_ONELINER,
    ADR037_OPERATIONAL_CLOSURE_STATUS,
)
from scripts.registry_adapters.state_contract import StateValidationResult, validate_unified_state  # noqa: E402


def write_github_step_summary(result: StateValidationResult) -> None:
    """Append ADR-037 closure + contract result to $GITHUB_STEP_SUMMARY when present."""
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    contract_status = "PASS" if result.passed else "FAIL"
    warnings = result.warnings or ["none"]
    blockers = result.blockers or ["none"]
    snap = result.snapshot or {}
    body = f"""## ADR-037 operational closure

| | |
|---|---|
| **STATUS** | **{ADR037_OPERATIONAL_CLOSURE_STATUS}** |
| Architecture | Frozen — computed state + contract only |
| Reference | `{ADR037_OPERATIONAL_CLOSURE_DOC}` |

> {ADR037_OPERATIONAL_CLOSURE_ONELINER}

### State contract (`{result.mode}`)

| | |
|---|---|
| Contract validation | **{contract_status}** |
| Phase | `{snap.get("phase", "—")}` |
| Stop-the-line | `{snap.get("stop_the_line", "—")}` |
| Active incidents | `{snap.get("active_incidents", "—")}` |
| Critical risks | `{", ".join(snap.get("critical_risks") or []) or "none"}` |

**Warnings:** {", ".join(warnings)}

**Blockers:** {", ".join(blockers)}
"""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description="ADR-037 unified state contract validation")
    parser.add_argument("--premerge", action="store_true", help="Strict checks for PR pipeline")
    parser.add_argument("--runtime", action="store_true", help="Observability/runtime checks (warnings only for drift gate)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-step-summary",
        action="store_true",
        help="Append closure banner to GITHUB_STEP_SUMMARY (no-op if unset)",
    )
    args = parser.parse_args()

    mode = "premerge" if args.premerge else "runtime"
    if args.premerge and args.runtime:
        mode = "premerge"

    result = validate_unified_state(mode=mode)

    if args.write_step_summary:
        write_github_step_summary(result)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        print(f"State contract {status} (mode={mode}, v{result.contract_version})")
        for check in result.checks:
            mark = "ok" if check["ok"] else "FAIL"
            print(f"  [{mark}] {check['check']}: {check.get('detail', '')}")
        for w in result.warnings:
            print(f"  warning: {w}")
        for b in result.blockers:
            print(f"  blocker: {b}")

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
