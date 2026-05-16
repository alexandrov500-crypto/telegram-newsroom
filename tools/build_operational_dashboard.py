#!/usr/bin/env python3
"""Build a static operational HTML dashboard from bundle + JSON reports (read-only)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(
        description="Static operational dashboard (single HTML file, no live UI, no frameworks)",
    )
    p.add_argument("--runtime-bundle", type=Path, default=None, help="runtime_bundle.zip (optional)")
    p.add_argument("--qualification-report", type=Path, default=None, help="release qualification JSON")
    p.add_argument("--regression-report", type=Path, default=None, help="compare_runtime_baseline JSON")
    p.add_argument("--retention-report", type=Path, default=None, help="runtime_retention JSON")
    p.add_argument("--output", required=True, type=Path, help="operational_dashboard.html")
    p.add_argument("--title", default="Operational dashboard", help="HTML title / H1")
    p.add_argument(
        "--include-json-snippets",
        action="store_true",
        help="Append bounded raw JSON snippets per section",
    )
    p.add_argument(
        "--strict",
        action="store_true",
        help="Non-zero exit if any input warnings (missing paths, corrupt JSON, bad zip)",
    )
    args = p.parse_args()

    from utils.operational_dashboard import (
        build_dashboard_payload,
        render_dashboard_html,
        strict_dashboard_exit_code,
    )

    payload = build_dashboard_payload(
        runtime_bundle=args.runtime_bundle.expanduser().resolve() if args.runtime_bundle else None,
        qualification_report=args.qualification_report.expanduser().resolve()
        if args.qualification_report
        else None,
        regression_report=args.regression_report.expanduser().resolve() if args.regression_report else None,
        retention_report=args.retention_report.expanduser().resolve() if args.retention_report else None,
        title=str(args.title),
    )
    html = render_dashboard_html(payload, include_json_snippets=bool(args.include_json_snippets))
    out = args.output.expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    code = strict_dashboard_exit_code(payload, strict=bool(args.strict))
    nw = len(payload.get("input_warnings") or [])
    print(f"wrote={out} input_warnings={nw} exit_code={code}")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(main())
