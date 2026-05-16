#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from sqlalchemy.engine import make_url


def _sqlite_path_from_database_url(url: str) -> Path | None:
    try:
        u = make_url(url.strip())
    except Exception:
        return None
    if u.get_driver_name() not in ("sqlite", "aiosqlite"):
        return None
    db = (u.database or "").strip()
    if not db or db == ":memory:":
        return None
    p = Path(db)
    if not p.is_absolute():
        return (Path.cwd() / p).resolve()
    return p.resolve()


def _collect_runtime_files(runtime_dir: Path) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    if not runtime_dir.is_dir():
        return out
    for p in sorted(runtime_dir.rglob("*")):
        if p.is_file() and p.suffix in {".json", ".txt"}:
            rel = p.relative_to(runtime_dir).as_posix()
            if rel.startswith(".."):
                continue
            out.append((f"runtime/{rel}", p))
    return out


def _write_metadata(path: Path, *, database_url_hint: str, runtime_dir: str, extra: dict[str, Any]) -> None:
    meta = {
        "schema_version": 1,
        "created_unix": time.time(),
        "created_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "database_url_hint": database_url_hint,
        "runtime_state_dir": runtime_dir,
        **extra,
    }
    path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")


def cmd_backup_create(args: argparse.Namespace) -> int:
    from app.config import load_settings
    from utils.editorial_analytics import export_editorial_analytics
    from utils.metrics import export_snapshot

    settings = load_settings()
    db_path = _sqlite_path_from_database_url(settings.database_url)
    if db_path is None or not db_path.is_file():
        print("backup-create: SQLite file not found for DATABASE_URL", file=sys.stderr)
        return 2

    backup_root = Path(
        os.environ.get("NEWSROOM_BACKUP_DIR", str(Path(settings.runtime_state_dir).resolve().parent / "backups"))
    )
    backup_root.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    final_zip = backup_root / f"newsroom_backup_{ts}.zip"
    tmp_zip = backup_root / f"newsroom_backup_{ts}.zip.partial"

    rt = Path(settings.runtime_state_dir).expanduser().resolve()

    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    ed = export_editorial_analytics(ctr)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        shutil.copy2(db_path, td_path / "newsroom.db")
        meta_path = td_path / "metadata.json"
        _write_metadata(
            meta_path,
            database_url_hint=f"sqlite:{db_path.name}",
            runtime_dir=str(rt),
            extra={"metrics_counters": ctr, "editorial_analytics": ed},
        )
        with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(td_path / "newsroom.db", arcname="database/newsroom.db")
            zf.write(meta_path, arcname="metadata.json")
            for arc, fp in _collect_runtime_files(rt):
                zf.write(fp, arcname=arc)
        tmp_zip.replace(final_zip)

    if args.max_backups and args.max_backups > 0:
        files = sorted(backup_root.glob("newsroom_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[args.max_backups :]:
            try:
                old.unlink()
            except OSError:
                pass

    print(str(final_zip))
    return 0


def cmd_backup_list(args: argparse.Namespace) -> int:
    from app.config import load_settings

    settings = load_settings()
    backup_root = Path(
        os.environ.get("NEWSROOM_BACKUP_DIR", str(Path(settings.runtime_state_dir).resolve().parent / "backups"))
    )
    if not backup_root.is_dir():
        print("no backup directory")
        return 0
    rows = sorted(backup_root.glob("newsroom_backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if args.json:
        print(json.dumps([{"path": str(p), "bytes": p.stat().st_size} for p in rows[: args.limit]], indent=2))
        return 0
    for p in rows[: args.limit]:
        print(f"{p.stat().st_size}\t{p.name}")
    return 0


def cmd_backup_validate(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        print("missing zip", file=sys.stderr)
        return 2
    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            if bad:
                print(f"corrupt member: {bad}", file=sys.stderr)
                return 3
            names = set(zf.namelist())
            if "metadata.json" not in names:
                print("missing metadata.json", file=sys.stderr)
                return 3
            meta = json.loads(zf.read("metadata.json").decode("utf-8"))
            if "database/newsroom.db" not in names:
                print("missing database/newsroom.db", file=sys.stderr)
                return 3
            with tempfile.TemporaryDirectory() as td:
                td_path = Path(td)
                zf.extract("database/newsroom.db", path=td_path)
                con = sqlite3.connect(str(td_path / "database" / "newsroom.db"))
                try:
                    row = con.execute("PRAGMA quick_check").fetchone()
                finally:
                    con.close()
                if not row or row[0] != "ok":
                    print(f"sqlite quick_check: {row}", file=sys.stderr)
                    return 4
    except zipfile.BadZipFile as exc:
        print(f"bad zip: {exc}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps({"ok": True, "metadata_keys": sorted(meta.keys())}, indent=2))
        return 0
    print("ok")
    return 0


def cmd_backup_restore(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if not path.is_file():
        print("missing zip", file=sys.stderr)
        return 2
    from app.config import load_settings

    settings = load_settings()
    db_path = _sqlite_path_from_database_url(settings.database_url)
    if db_path is None:
        print("restore only supports file SQLite URLs", file=sys.stderr)
        return 2
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "r") as zf:
        if "database/newsroom.db" not in zf.namelist():
            print("archive missing database/newsroom.db", file=sys.stderr)
            return 3
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            zf.extract("database/newsroom.db", path=td_path)
            src = td_path / "database" / "newsroom.db"
            backup_prev = db_path.with_suffix(db_path.suffix + ".pre_restore")
            if db_path.is_file():
                shutil.copy2(db_path, backup_prev)
            shutil.copy2(src, db_path)
    rt = Path(settings.runtime_state_dir).expanduser().resolve()
    if args.with_runtime:
        with zipfile.ZipFile(path, "r") as zf:
            for name in zf.namelist():
                if not name.startswith("runtime/") or name.endswith("/"):
                    continue
                dest = rt / name[len("runtime/") :]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(name))
    print(f"restored database to {db_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Newsroom backup / restore (local files only)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_c = sub.add_parser("backup-create", help="Create timestamped backup archive")
    p_c.add_argument("--max-backups", type=int, default=0, help="Keep only N newest backups (0=unlimited)")
    p_c.set_defaults(func=cmd_backup_create)

    p_l = sub.add_parser("backup-list", help="List backup archives")
    p_l.add_argument("--limit", type=int, default=50)
    p_l.add_argument("--json", action="store_true")
    p_l.set_defaults(func=cmd_backup_list)

    p_v = sub.add_parser("backup-validate", help="Validate backup zip integrity + SQLite quick_check")
    p_v.add_argument("path", type=str)
    p_v.add_argument("--json", action="store_true")
    p_v.set_defaults(func=cmd_backup_validate)

    p_r = sub.add_parser("backup-restore", help="Restore database from backup (optionally runtime files)")
    p_r.add_argument("path", type=str)
    p_r.add_argument("--with-runtime", action="store_true", help="Also restore runtime/* members into RUNTIME_STATE_DIR")
    p_r.set_defaults(func=cmd_backup_restore)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
