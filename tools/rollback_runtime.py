#!/usr/bin/env python3
"""Rollback runtime: snapshot restore + operational mode + manifest verify."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def list_manifests(runtime_dir: str) -> list[dict[str, Any]]:
    from ops.resilience.deployment_manifest import load_deployment_manifest
    from ops.resilience.snapshot import list_snapshots

    current = load_deployment_manifest(runtime_dir)
    snaps = list_snapshots(runtime_dir)
    out: list[dict[str, Any]] = []
    if current:
        out.append({"type": "deployment_manifest", "current": True, **current})
    for s in snaps:
        out.append({"type": "full_snapshot", **s})
    return out


def compare_manifests(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(a) | set(b))
    diff = {k: {"a": a.get(k), "b": b.get(k)} for k in keys if a.get(k) != b.get(k)}
    return {"changed_fields": diff, "field_count": len(diff)}


def cmd_list(_args: argparse.Namespace) -> int:
    from app.config import load_settings

    settings = load_settings()
    print(json.dumps(list_manifests(settings.runtime_state_dir), indent=2, default=str))
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    from app.config import load_settings

    settings = load_settings()
    rd = settings.runtime_state_dir
    cur = __import__("ops.resilience.deployment_manifest", fromlist=["load_deployment_manifest"]).load_deployment_manifest(rd)
    snap_meta = {}
    archive = Path(args.snapshot).expanduser()
    if not archive.is_file():
        archive = Path(rd) / "full_snapshots" / args.snapshot
    if archive.is_file():
        import tarfile
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(td, filter="data")
            mf = Path(td) / "MANIFEST.json"
            if mf.is_file():
                snap_meta = json.loads(mf.read_text(encoding="utf-8")).get("snapshot") or {}
    print(json.dumps(compare_manifests(cur, snap_meta), indent=2, default=str))
    return 0


def cmd_rollback(args: argparse.Namespace) -> int:
    from app.config import load_settings
    from app.operational_mode import OperationalMode, set_operational_mode
    from ops.resilience.snapshot import restore_snapshot

    settings = load_settings()
    archive = Path(args.snapshot).expanduser()
    if not archive.is_file():
        archive = Path(settings.runtime_state_dir) / "full_snapshots" / args.snapshot
    if not archive.is_file():
        print(f"Snapshot not found: {args.snapshot}", file=sys.stderr)
        return 2
    report = restore_snapshot(
        archive,
        runtime_dir=settings.runtime_state_dir,
        database_url=settings.database_url,
        dry_run=bool(args.dry_run),
    )
    if report.get("errors"):
        print(json.dumps(report, indent=2))
        return 1
    if not args.dry_run:
        mode = OperationalMode.RECOVERY if args.recovery_mode else OperationalMode.PRODUCTION
        set_operational_mode(settings.runtime_state_dir, mode, reason="rollback_runtime")
    print(json.dumps({"ok": True, "dry_run": args.dry_run, "report": report}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Runtime rollback tooling")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="List manifests and snapshots").set_defaults(func=cmd_list)
    p_cmp = sub.add_parser("compare", help="Compare current manifest vs snapshot")
    p_cmp.add_argument("snapshot")
    p_cmp.set_defaults(func=cmd_compare)
    p_rb = sub.add_parser("rollback", help="Restore snapshot atomically")
    p_rb.add_argument("snapshot")
    p_rb.add_argument("--dry-run", action="store_true")
    p_rb.add_argument("--recovery-mode", action="store_true", help="Set operational mode recovery after restore")
    p_rb.set_defaults(func=cmd_rollback)
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
