#!/usr/bin/env python3
"""Generate static operations index HTML."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from utils.ops_analytics import default_reports_dir
from utils.ops_bundle import default_bundle_root
from utils.ops_index import build_ops_index_html
from utils.ops_release_kit import default_release_kit_root


def main() -> int:
    p = argparse.ArgumentParser(description="Static ops index (offline HTML)")
    p.add_argument("--reports-dir", default="")
    p.add_argument("--release-kit-root", default="")
    p.add_argument("--bundle-root", default="")
    p.add_argument("--output", default="")
    args = p.parse_args()

    reports = Path(args.reports_dir) if args.reports_dir else default_reports_dir(REPO)
    reports.mkdir(parents=True, exist_ok=True)
    html = build_ops_index_html(
        reports_dir=reports,
        release_kit_root=Path(args.release_kit_root) if args.release_kit_root else default_release_kit_root(REPO),
        bundle_root=Path(args.bundle_root) if args.bundle_root else default_bundle_root(REPO),
    )
    out = Path(args.output) if args.output else reports / "index.html"
    out.write_text(html, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
