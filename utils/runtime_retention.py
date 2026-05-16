"""Filesystem retention (production-lite, deterministic, no daemon, no network).

Combines (1) in-process ``snapshot_*.json`` pruning for ``runtime_state_store`` and
(2) optional directory cleanup for CI artifact roots (see ``tools/runtime_retention.py``).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

RootKind = Literal["artifacts", "baselines", "reports"]


@dataclass(frozen=True)
class FileCandidate:
    """Regular file eligible for retention (non-symlink, top-level under a root)."""

    path: Path
    root_kind: RootKind
    mtime: float
    size_bytes: int


def _is_retention_artifact_basename(name: str) -> bool:
    lower = name.lower()
    if lower.endswith(".zip"):
        return True
    if not lower.endswith(".json"):
        return False
    return "regression" in lower or "qualification" in lower


def _is_retention_baseline_basename(name: str) -> bool:
    return name.lower().endswith(".zip")


def _is_retention_report_basename(name: str, *, include_html: bool) -> bool:
    lower = name.lower()
    if lower.endswith(".json"):
        return any(k in lower for k in ("soak", "benchmark", "integrity"))
    if include_html and lower.endswith(".html"):
        return any(k in lower for k in ("soak", "benchmark", "integrity"))
    return False


def _matches_root(name: str, root_kind: RootKind, *, include_html: bool) -> bool:
    if root_kind == "artifacts":
        return _is_retention_artifact_basename(name)
    if root_kind == "baselines":
        return _is_retention_baseline_basename(name)
    return _is_retention_report_basename(name, include_html=include_html)


def scan_runtime_artifacts(
    *,
    artifacts_dir: Path | None,
    baselines_dir: Path | None,
    reports_dir: Path | None,
    include_html: bool,
) -> tuple[list[FileCandidate], list[str]]:
    """
    List **top-level** regular files under each configured root that match retention basename rules.

    Subdirectories are not entered; symlinks are ignored for matching (see ``scan_skipped_entries``).
    """
    roots: list[tuple[RootKind, Path | None]] = [
        ("artifacts", artifacts_dir),
        ("baselines", baselines_dir),
        ("reports", reports_dir),
    ]
    candidates: list[FileCandidate] = []
    warnings: list[str] = []
    for kind, root in roots:
        if root is None:
            continue
        rp = root.expanduser()
        try:
            rp = rp.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            warnings.append(f"resolve_failed:{kind}:{root}:{exc!r}")
            continue
        if not rp.exists():
            warnings.append(f"missing_dir:{kind}:{rp}")
            continue
        if not rp.is_dir():
            warnings.append(f"not_a_directory:{kind}:{rp}")
            continue
        try:
            names = sorted(os.listdir(rp))
        except OSError as exc:
            warnings.append(f"listdir_failed:{kind}:{rp}:{exc!r}")
            continue
        for name in names:
            child = rp / name
            try:
                if child.is_symlink():
                    continue
                if child.is_dir():
                    continue
                if not child.is_file():
                    continue
            except OSError as exc:
                warnings.append(f"entry_inspect_failed:{child}:{exc!r}")
                continue
            if not _matches_root(name, kind, include_html=include_html):
                continue
            try:
                st = child.stat()
                mtime = float(st.st_mtime)
                size = int(st.st_size)
            except OSError as exc:
                warnings.append(f"stat_failed:{child}:{exc!r}")
                continue
            candidates.append(FileCandidate(path=child, root_kind=kind, mtime=mtime, size_bytes=size))
    candidates.sort(key=lambda c: str(c.path))
    return candidates, sorted(set(warnings))


def scan_skipped_entries(
    *,
    artifacts_dir: Path | None,
    baselines_dir: Path | None,
    reports_dir: Path | None,
) -> tuple[list[str], list[str]]:
    """Symlinks and directories directly under each root (reporting only)."""
    roots: list[tuple[RootKind, Path | None]] = [
        ("artifacts", artifacts_dir),
        ("baselines", baselines_dir),
        ("reports", reports_dir),
    ]
    skipped: list[str] = []
    warnings: list[str] = []
    for kind, root in roots:
        if root is None:
            continue
        rp = root.expanduser()
        try:
            rp = rp.resolve(strict=False)
        except (OSError, RuntimeError) as exc:
            warnings.append(f"resolve_failed:{kind}:{root}:{exc!r}")
            continue
        if not rp.is_dir():
            continue
        try:
            names = sorted(os.listdir(rp))
        except OSError as exc:
            warnings.append(f"listdir_failed:{kind}:{rp}:{exc!r}")
            continue
        for name in names:
            child = rp / name
            try:
                if child.is_symlink():
                    skipped.append(f"symlink:{child}")
                    continue
                if child.is_dir():
                    skipped.append(f"directory:{child}")
            except OSError as exc:
                warnings.append(f"entry_inspect_failed:{child}:{exc!r}")
    return sorted(skipped), sorted(set(warnings))


def classify_retention_candidates(
    candidates: list[FileCandidate],
    *,
    retain_count: int,
    max_age_days: float,
    now: float | None = None,
) -> tuple[list[FileCandidate], list[FileCandidate]]:
    """
    Return ``(to_retain, to_delete)`` with deterministic ordering.

    1. If ``max_age_days`` > 0, files with mtime older than the cutoff are always deleted.
    2. Among the rest, keep the newest ``retain_count`` files (``mtime`` desc, path asc tie-break).
    3. Any remaining file in that pool is deleted.
    """
    t0 = float(time.time() if now is None else now)
    if retain_count < 0:
        raise ValueError("retain_count must be non-negative")
    if max_age_days < 0:
        raise ValueError("max_age_days must be non-negative")

    if max_age_days > 0:
        cutoff = t0 - max_age_days * 86400.0
        too_old_paths = {str(c.path) for c in candidates if c.mtime < cutoff}
    else:
        too_old_paths = set()

    ordered = sorted(candidates, key=lambda c: (-c.mtime, str(c.path)))
    pool = [c for c in ordered if str(c.path) not in too_old_paths]
    pool_sorted = sorted(pool, key=lambda c: (-c.mtime, str(c.path)))
    retained = pool_sorted[: int(retain_count)]
    retained_paths = {str(c.path) for c in retained}

    to_delete_paths: set[str] = set(too_old_paths)
    for c in pool_sorted[int(retain_count) :]:
        to_delete_paths.add(str(c.path))

    to_delete = sorted([c for c in candidates if str(c.path) in to_delete_paths], key=lambda c: str(c.path))
    retained_sorted = sorted(retained, key=lambda c: str(c.path))
    return retained_sorted, to_delete


def apply_retention_policy(
    to_delete: list[FileCandidate],
    *,
    dry_run: bool,
    unlink: Callable[[Path], None] | None = None,
) -> tuple[list[str], list[str]]:
    """
    Delete files unless ``dry_run``.

    Returns ``(deleted_or_would_delete_paths, warnings)`` as sorted lists.
    """
    warnings: list[str] = []
    deleted: list[str] = []
    for c in sorted(to_delete, key=lambda x: str(x.path)):
        p = c.path
        if dry_run:
            deleted.append(str(p))
            continue
        try:
            if p.is_symlink():
                warnings.append(f"skip_delete_symlink_race:{p}")
                continue
            if unlink is not None:
                unlink(p)
            else:
                p.unlink(missing_ok=True)
            deleted.append(str(p))
        except OSError as exc:
            warnings.append(f"unlink_failed:{p}:{exc!r}")
    return sorted(deleted), sorted(warnings)


def build_retention_report(
    *,
    scanned: list[FileCandidate],
    retained: list[FileCandidate],
    deleted: list[FileCandidate],
    skipped_files: list[str],
    dry_run: bool,
    extra_warnings: list[str],
    deleted_paths_actual: list[str] | None = None,
) -> dict[str, Any]:
    """JSON-serializable retention report."""
    scanned_paths = sorted({str(c.path) for c in scanned})
    retained_paths = sorted({str(c.path) for c in retained})
    planned_delete = sorted({str(c.path) for c in deleted})
    deleted_paths = sorted(deleted_paths_actual) if deleted_paths_actual is not None else list(planned_delete)

    bytes_before = sum(int(c.size_bytes) for c in scanned)
    deleted_sizes = {str(c.path): int(c.size_bytes) for c in deleted}
    reclaimed = sum(deleted_sizes.get(p, 0) for p in deleted_paths)
    bytes_after = int(bytes_before) - int(reclaimed)

    return {
        "deleted_files": deleted_paths,
        "dry_run": bool(dry_run),
        "reclaimed_bytes": int(reclaimed),
        "retained_files": retained_paths,
        "scanned_files": scanned_paths,
        "skipped_files": sorted(skipped_files),
        "total_bytes_after": int(bytes_after),
        "total_bytes_before": int(bytes_before),
        "warnings": sorted(set(extra_warnings)),
    }


def render_retention_summary(report: dict[str, Any]) -> str:
    n_scan = len(report.get("scanned_files") or [])
    n_ret = len(report.get("retained_files") or [])
    n_del = len(report.get("deleted_files") or [])
    n_skip = len(report.get("skipped_files") or [])
    reclaimed = int(report.get("reclaimed_bytes") or 0)
    mb = reclaimed / (1024 * 1024) if reclaimed else 0.0
    dry = bool(report.get("dry_run"))
    lines = [
        "Runtime retention summary",
        "",
        f"Files scanned (eligible): {n_scan}",
        f"Files retained: {n_ret}",
        f"Files deleted: {n_del}",
        f"Files skipped (symlinks/dirs): {n_skip}",
        (
            f"Space reclaimed: {reclaimed} bytes ({mb:.1f} MB)"
            if reclaimed
            else "Space reclaimed: 0 bytes (0.0 MB)"
        ),
        "",
        f"Dry-run: {str(dry).lower()}",
    ]
    warns = report.get("warnings") or []
    if warns:
        lines.extend(["", "Warnings:"])
        for w in warns[:24]:
            lines.append(f"  {w}")
    return "\n".join(lines) + "\n"


def run_retention_pass(
    *,
    artifacts_dir: Path | None,
    baselines_dir: Path | None,
    reports_dir: Path | None,
    retain_count: int,
    max_age_days: float,
    include_html: bool,
    dry_run: bool,
    now: float | None = None,
    unlink: Callable[[Path], None] | None = None,
) -> dict[str, Any]:
    """
    Scan → classify → delete (or dry-run). ``now`` is for tests (mtime age cut).

    ``retain_count`` and ``max_age_days`` apply **independently** within each root
    (artifacts / baselines / reports), not as a single merged pool.
    """
    scanned, w_scan = scan_runtime_artifacts(
        artifacts_dir=artifacts_dir,
        baselines_dir=baselines_dir,
        reports_dir=reports_dir,
        include_html=include_html,
    )
    skipped, w_skip = scan_skipped_entries(
        artifacts_dir=artifacts_dir,
        baselines_dir=baselines_dir,
        reports_dir=reports_dir,
    )
    retained: list[FileCandidate] = []
    to_delete: list[FileCandidate] = []
    for kind in ("artifacts", "baselines", "reports"):
        group = [c for c in scanned if c.root_kind == kind]
        r, d = classify_retention_candidates(
            group,
            retain_count=retain_count,
            max_age_days=max_age_days,
            now=now,
        )
        retained.extend(r)
        to_delete.extend(d)
    retained.sort(key=lambda c: str(c.path))
    to_delete.sort(key=lambda c: str(c.path))
    del_paths, w_del = apply_retention_policy(to_delete, dry_run=dry_run, unlink=unlink)
    extra = sorted(set(w_scan + w_skip + w_del))
    return build_retention_report(
        scanned=scanned,
        retained=retained,
        deleted=to_delete,
        skipped_files=skipped,
        dry_run=dry_run,
        extra_warnings=extra,
        deleted_paths_actual=None if dry_run else del_paths,
    )


def strict_exit_code(report: dict[str, Any], *, strict: bool) -> int:
    if not strict:
        return 0
    return 1 if bool(report.get("warnings")) else 0


# --- In-process runtime snapshot retention (``runtime_state_store``) ---------------------------

_SNAPSHOT_GLOB = "snapshot_*.json"


def list_snapshot_files(directory: Path) -> list[Path]:
    """Non-recursive ``snapshot_*.json`` files (no symlinks), sorted by path for stable iteration."""
    out: list[Path] = []
    try:
        d = directory.expanduser().resolve(strict=False)
    except OSError:
        return []
    if not d.is_dir():
        return []
    for p in sorted(d.glob(_SNAPSHOT_GLOB), key=lambda x: str(x)):
        try:
            if p.is_symlink() or not p.is_file():
                continue
            out.append(p)
        except OSError:
            continue
    return out


def cleanup_old_runtime_snapshots(settings: Any) -> int:
    """
    Delete excess ``snapshot_*.json`` files under ``settings.runtime_state_dir``.

    Policy (deterministic):
    * Age: if ``runtime_snapshots_max_age_hours`` > 0, delete when ``(now - mtime)`` exceeds that many
      hours. If the setting is ``<= 0`` (tests), treat the threshold as **1 second** so only stale
      files are removed without wiping freshly written snapshots.
    * Count: keep at most ``runtime_snapshots_max_count`` newest files (mtime desc, path asc).
    * Bytes: among kept files, drop oldest until total size is ``<= runtime_snapshots_max_storage_bytes``.
    """
    try:
        d = Path(str(getattr(settings, "runtime_state_dir", ""))).expanduser().resolve(strict=False)
    except OSError:
        return 0
    if not d.is_dir():
        return 0

    paths = list_snapshot_files(d)
    if not paths:
        return 0

    now = time.time()
    max_count = max(0, int(getattr(settings, "runtime_snapshots_max_count", 0) or 0))
    max_age_h = int(getattr(settings, "runtime_snapshots_max_age_hours", 0) or 0)
    max_bytes = max(0, int(getattr(settings, "runtime_snapshots_max_storage_bytes", 0) or 0))

    if max_age_h > 0:
        age_threshold_sec = float(max_age_h) * 3600.0
    else:
        age_threshold_sec = 1.0

    rows: list[tuple[Path, float, int]] = []
    for p in paths:
        try:
            st = p.stat()
            rows.append((p, float(st.st_mtime), int(st.st_size)))
        except OSError:
            continue

    rows.sort(key=lambda r: (-r[1], str(r[0])))
    aged_out = {p for p, mt, _sz in rows if now - mt >= age_threshold_sec}
    pool = [(p, mt, sz) for p, mt, sz in rows if p not in aged_out]
    pool.sort(key=lambda r: (-r[1], str(r[0])))
    keep = pool[:max_count] if max_count > 0 else []
    overflow = pool[max_count:] if max_count > 0 else pool
    delete_set: set[Path] = set(aged_out)
    delete_set.update(p for p, _, _ in overflow)

    keep_list = sorted(keep, key=lambda r: (r[1], str(r[0])))
    total = sum(sz for _, _, sz in keep_list)
    while total > max_bytes and keep_list:
        p, _mt, sz = keep_list.pop(0)
        delete_set.add(p)
        total -= sz

    deleted_n = 0
    for p in sorted(delete_set, key=str):
        try:
            if p.is_symlink():
                continue
            p.unlink(missing_ok=True)
            deleted_n += 1
        except OSError:
            continue
    return deleted_n
