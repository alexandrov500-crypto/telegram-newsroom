#!/usr/bin/env python3
"""Export immutable incident bundle for RCA."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env, project_root
from bot.ops_forensics.bundles import export_incident_bundle


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser()
    p.add_argument("--incident", required=True, help="incident bundle id (label)")
    p.add_argument("--publish-id", type=int, default=None)
    p.add_argument("--correlation-id", default=None)
    p.add_argument("--log", type=Path, default=project_root() / "var/log/pilot-operator.log")
    args = p.parse_args()

    summary = export_incident_bundle(
        incident_id=args.incident,
        publish_id=args.publish_id,
        correlation_id=args.correlation_id,
        log_path=args.log if args.log.is_file() else None,
    )
    print(json.dumps(summary, indent=2))
    print(f"\nBundle: {summary['export_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
