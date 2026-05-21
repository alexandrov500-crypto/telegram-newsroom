"""Full runtime snapshot create/restore with checksum manifest (no secrets)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

from app.versioning import public_metadata
from ops.resilience.paths import snapshots_dir
from sqlalchemy.engine import make_url

SNAPSHOT_FORMAT_VERSION = 1
_SECRET_SUFFIXES = ("TOKEN", "KEY", "SECRET", "PASSWORD", "SESSION", "HASH", "API_KEY")


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
    return p.resolve() if p.is_absolute() else (Path.cwd() / p).resolve()


def _config_fingerprint() -> str:
    """Hash non-secret env keys for reproducibility."""
    keys = sorted(
        k
        for k in os.environ
        if k.startswith(("NEWSROOM_", "RUNTIME_", "PIPELINE_", "EDITORIAL_", "DRY_RUN", "SOAK_"))
        and not any(s in k.upper() for s in _SECRET_SUFFIXES)
    )
    blob = "\n".join(f"{k}={os.environ.get(k, '')[:80]}" for k in keys)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def collect_snapshot_paths(runtime_dir: Path) -> list[Path]:
    """All recoverable runtime files (governance, ledger, policies, replay snapshots)."""
    paths: list[Path] = []
    if not runtime_dir.is_dir():
        return paths
    include_suffixes = {".json", ".jsonl", ".txt"}
    skip_dirs = {"full_snapshots", "locks"}
    for p in sorted(runtime_dir.rglob("*")):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(runtime_dir).parts
        if rel_parts and rel_parts[0] in skip_dirs:
            continue
        if p.suffix.lower() not in include_suffixes:
            continue
        paths.append(p)
    return paths


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def create_snapshot(
    *,
    runtime_dir: str,
    database_url: str,
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    rt = Path(runtime_dir).expanduser().resolve()
    out_dir = snapshots_dir(str(rt))
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    snap_id = f"snap_{ts}_{uuid.uuid4().hex[:8]}"
    archive = out_dir / f"{snap_id}.tar.gz"
    tmp = out_dir / f"{snap_id}.tar.gz.partial"

    files = collect_snapshot_paths(rt)
    manifest_files: list[dict[str, Any]] = []

    meta: dict[str, Any] = {
        "snapshot_id": snap_id,
        "format_version": SNAPSHOT_FORMAT_VERSION,
        "created_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "created_unix": time.time(),
        "runtime_state_dir": str(rt),
        "config_fingerprint": _config_fingerprint(),
        "compatibility": public_metadata(),
        "file_count": 0,
        **(extra_metadata or {}),
    }

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        staging = td_path / "runtime"
        staging.mkdir(parents=True)
        for src in files:
            rel = src.relative_to(rt).as_posix()
            dest = staging / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            manifest_files.append({"path": f"runtime/{rel}", "sha256": _sha256_file(dest), "size": dest.stat().st_size})

        db_path = _sqlite_path_from_database_url(database_url)
        if db_path and db_path.is_file():
            db_dest = td_path / "database" / "newsroom.db"
            db_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(db_path, db_dest)
            manifest_files.append({"path": "database/newsroom.db", "sha256": _sha256_file(db_dest), "size": db_dest.stat().st_size})
            meta["database_included"] = True
        else:
            meta["database_included"] = False

        meta["file_count"] = len(manifest_files)
        manifest = {"snapshot": meta, "files": manifest_files}
        (td_path / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        with tarfile.open(tmp, "w:gz") as tar:
            tar.add(td_path / "MANIFEST.json", arcname="MANIFEST.json")
            if (td_path / "database").is_dir():
                tar.add(td_path / "database", arcname="database")
            tar.add(staging, arcname="runtime")

    tmp.replace(archive)
    _prune_snapshots(out_dir)
    return archive


def _prune_snapshots(out_dir: Path) -> None:
    max_n = int(os.getenv("RUNTIME_FULL_SNAPSHOT_MAX", "12"))
    max_bytes = int(os.getenv("RUNTIME_FULL_SNAPSHOT_MAX_BYTES", str(512_000_000)))
    files = sorted(out_dir.glob("snap_*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = sum(p.stat().st_size for p in files)
    while len(files) > max_n or total > max_bytes:
        victim = files.pop()
        try:
            total -= victim.stat().st_size
            victim.unlink()
        except OSError:
            break


def restore_snapshot(
    archive_path: Path,
    *,
    runtime_dir: str,
    database_url: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    archive_path = archive_path.expanduser().resolve()
    if not archive_path.is_file():
        raise FileNotFoundError(str(archive_path))
    rt = Path(runtime_dir).expanduser().resolve()
    report: dict[str, Any] = {"archive": str(archive_path), "restored_files": 0, "dry_run": dry_run, "errors": []}

    with tempfile.TemporaryDirectory() as td:
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(td, filter="data")
        td_path = Path(td)
        manifest_path = td_path / "MANIFEST.json"
        if not manifest_path.is_file():
            raise ValueError("Snapshot missing MANIFEST.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        snap_meta = manifest.get("snapshot") or {}
        compat = snap_meta.get("compatibility") or {}
        current = public_metadata()
        if int(compat.get("runtime_state_schema_version", 1)) > int(current["runtime_state_schema_version"]):
            report["errors"].append("snapshot_schema_newer_than_runtime")
            raise ValueError("Snapshot schema newer than this runtime — upgrade app first")

        staging = td_path / "runtime"
        if staging.is_dir():
            for src in staging.rglob("*"):
                if not src.is_file():
                    continue
                rel = src.relative_to(staging)
                dest = rt / rel
                if not dry_run:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                report["restored_files"] = int(report["restored_files"]) + 1

        db_src = td_path / "database" / "newsroom.db"
        if db_src.is_file():
            db_dest = _sqlite_path_from_database_url(database_url)
            if db_dest is None:
                report["errors"].append("database_restore_skipped_non_sqlite")
            elif not dry_run:
                db_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(db_src, db_dest)
                try:
                    with sqlite3.connect(str(db_dest)) as conn:
                        conn.execute("PRAGMA integrity_check")
                except sqlite3.Error as exc:
                    report["errors"].append(f"sqlite_integrity: {exc}")
            report["database_restored"] = db_dest is not None and not dry_run

    report["snapshot_id"] = snap_meta.get("snapshot_id")
    report["compatibility"] = compat
    return report


def list_snapshots(runtime_dir: str) -> list[dict[str, Any]]:
    out_dir = snapshots_dir(runtime_dir)
    rows: list[dict[str, Any]] = []
    for p in sorted(out_dir.glob("snap_*.tar.gz"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = p.stat()
        rows.append({
            "name": p.name,
            "path": str(p),
            "size_bytes": st.st_size,
            "mtime_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)),
        })
    return rows
