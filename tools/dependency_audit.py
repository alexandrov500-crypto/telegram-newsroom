#!/usr/bin/env python3
"""Read-only dependency inventory and pin policy check."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

FORBIDDEN_PACKAGES = frozenset(
    {
        "pickle-mixin",
        "python-sqlite",
    }
)

ALLOW_UNPINNED = frozenset({"greenlet", "asyncpg", "redis", "psycopg"})


def _parse_requirements(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(.*)$", line)
        if not m:
            rows.append({"raw": line, "name": "?", "spec": line})
            continue
        name, spec = m.group(1), m.group(2).strip()
        rows.append({"name": name.lower(), "spec": spec, "raw": line})
    return rows


def audit_file(path: Path) -> dict[str, object]:
    rows = _parse_requirements(path)
    unpinned: list[str] = []
    forbidden: list[str] = []
    for r in rows:
        name = str(r.get("name") or "")
        spec = str(r.get("spec") or "")
        if name in FORBIDDEN_PACKAGES:
            forbidden.append(str(r.get("raw")))
        if name in ALLOW_UNPINNED:
            continue
        if spec.startswith(">=") and "==" not in spec:
            unpinned.append(str(r.get("raw")))
    status = "FAIL" if forbidden else ("WARNING" if unpinned else "OK")
    return {
        "path": str(path),
        "package_count": len(rows),
        "unpinned": unpinned,
        "forbidden": forbidden,
        "status": status,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--requirements", default=str(REPO / "requirements.txt"))
    p.add_argument("--dev-requirements", default=str(REPO / "requirements-dev.txt"))
    p.add_argument("--json-output", default="")
    p.add_argument("--strict", action="store_true", help="Fail on unpinned deps")
    args = p.parse_args()

    reports = [audit_file(Path(args.requirements)), audit_file(Path(args.dev_requirements))]
    overall = "OK"
    if any(r["status"] == "FAIL" for r in reports):
        overall = "FAIL"
    elif any(r["status"] == "WARNING" for r in reports):
        overall = "WARNING"
    if args.strict and overall != "OK":
        overall = "FAIL"

    out = {"status": overall, "reports": reports}
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(out, indent=2))
    return 0 if overall != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
