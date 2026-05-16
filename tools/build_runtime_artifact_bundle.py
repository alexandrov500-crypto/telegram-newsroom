#!/usr/bin/env python3
"""Build a reproducible zip bundle of runtime diagnostics (CI / postmortem)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(description="Build runtime_bundle.zip for CI or postmortem")
    p.add_argument("--runtime-dir", required=True, type=Path, help="RUNTIME_STATE_DIR root (JSON state + optional pre-rendered reports)")
    p.add_argument("--output", required=True, type=Path, help="Output .zip path")
    p.add_argument("--include-html", action="store_true", help="Expect soak_report.html in runtime-dir")
    p.add_argument("--fail-on-missing", action="store_true", help="Exit 1 if optional disk artifacts are absent")
    p.add_argument("--metadata-json", default="", help="Optional JSON file merged into environment + manifest_extra")
    args = p.parse_args()

    meta: dict = {}
    if args.metadata_json.strip():
        meta = json.loads(Path(args.metadata_json).read_text(encoding="utf-8"))

    from app.config import load_settings

    from utils.runtime_bundle import bundle_summary_lines, write_runtime_bundle

    runtime_dir = args.runtime_dir.expanduser().resolve()
    if not runtime_dir.is_dir():
        print(f"error: runtime-dir is not a directory: {runtime_dir}", file=sys.stderr)
        return 2

    settings = replace(load_settings(), runtime_state_dir=str(runtime_dir))
    try:
        manifest = write_runtime_bundle(
            runtime_dir,
            args.output,
            settings,
            include_html=bool(args.include_html),
            fail_on_missing=bool(args.fail_on_missing),
            metadata=meta,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    for line in bundle_summary_lines(args.output.resolve(), manifest):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
