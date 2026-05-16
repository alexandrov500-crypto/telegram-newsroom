from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from tests.conftest import minimal_test_settings
from utils.runtime_retention import (
    FileCandidate,
    apply_retention_policy,
    classify_retention_candidates,
    cleanup_old_runtime_snapshots,
    render_retention_summary,
    run_retention_pass,
    scan_runtime_artifacts,
    scan_skipped_entries,
    strict_exit_code,
)


def _touch(p: Path, *, size: int = 1, mtime: float | None = None) -> None:
    p.write_bytes(b"x" * size)
    if mtime is not None:
        os.utime(p, (mtime, mtime))


def test_retain_newest_files_per_root(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    now = 1_700_000_000.0
    for i, name in enumerate(["a.zip", "b.zip", "c.zip"]):
        _touch(art / name, size=10 + i, mtime=now + i)
    rep = run_retention_pass(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        retain_count=2,
        max_age_days=0.0,
        include_html=False,
        dry_run=False,
        now=now + 10,
    )
    assert len(rep["scanned_files"]) == 3
    assert len(rep["retained_files"]) == 2
    assert len(rep["deleted_files"]) == 1
    assert str(art / "a.zip") in rep["deleted_files"]
    assert rep["total_bytes_before"] == 10 + 11 + 12
    assert not rep["warnings"]


def test_delete_old_files_by_age(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    now = 1_700_000_000.0
    _touch(art / "old.zip", size=100, mtime=now - 10 * 86400)
    _touch(art / "new.zip", size=50, mtime=now)
    rep = run_retention_pass(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        retain_count=10,
        max_age_days=5.0,
        include_html=False,
        dry_run=False,
        now=now,
    )
    assert str(art / "old.zip") in rep["deleted_files"]
    assert str(art / "new.zip") in rep["retained_files"]
    assert rep["reclaimed_bytes"] == 100


def test_max_age_days_zero_disables_age_cut(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    now = 1_700_000_000.0
    _touch(art / "old.zip", mtime=now - 100 * 86400)
    _touch(art / "new.zip", mtime=now)
    rep = run_retention_pass(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        retain_count=2,
        max_age_days=0.0,
        include_html=False,
        dry_run=False,
        now=now,
    )
    assert len(rep["retained_files"]) == 2
    assert rep["deleted_files"] == []


def test_dry_run_no_delete(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    now = 1_700_000_000.0
    _touch(art / "a.zip", mtime=now)
    _touch(art / "b.zip", mtime=now + 1)
    rep = run_retention_pass(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        retain_count=1,
        max_age_days=0.0,
        include_html=False,
        dry_run=True,
        now=now + 5,
    )
    assert rep["dry_run"] is True
    assert str(art / "a.zip") in rep["deleted_files"]
    assert (art / "a.zip").is_file()
    assert (art / "b.zip").is_file()


def test_include_html_false_skips_html(tmp_path: Path) -> None:
    rep_dir = tmp_path / "reports"
    rep_dir.mkdir()
    _touch(rep_dir / "soak_report.json", mtime=1_700_000_000.0)
    _touch(rep_dir / "soak_report.html", mtime=1_700_000_000.0)
    scanned, _ = scan_runtime_artifacts(
        artifacts_dir=None,
        baselines_dir=None,
        reports_dir=rep_dir,
        include_html=False,
    )
    assert len(scanned) == 1
    assert scanned[0].path.name == "soak_report.json"


def test_include_html_true_includes_html(tmp_path: Path) -> None:
    rep_dir = tmp_path / "reports"
    rep_dir.mkdir()
    _touch(rep_dir / "benchmark_report.html", mtime=1_700_000_000.0)
    scanned, _ = scan_runtime_artifacts(
        artifacts_dir=None,
        baselines_dir=None,
        reports_dir=rep_dir,
        include_html=True,
    )
    assert len(scanned) == 1


def test_missing_directories_graceful(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    rep = run_retention_pass(
        artifacts_dir=missing,
        baselines_dir=tmp_path / "also_missing",
        reports_dir=None,
        retain_count=5,
        max_age_days=0.0,
        include_html=False,
        dry_run=True,
        now=1_700_000_000.0,
    )
    assert rep["scanned_files"] == []
    assert len(rep["warnings"]) >= 1
    assert any("missing_dir" in w for w in rep["warnings"])


def test_symbolic_links_skipped(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    real = art / "real.zip"
    _touch(real, mtime=1_700_000_000.0)
    link = art / "link.zip"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlinks not supported")
    scanned, _ = scan_runtime_artifacts(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        include_html=False,
    )
    assert len(scanned) == 1
    skipped, _ = scan_skipped_entries(artifacts_dir=art, baselines_dir=None, reports_dir=None)
    assert any("symlink:" in s for s in skipped)


def test_deterministic_ordering(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    t = 1_700_000_000.0
    _touch(art / "a.zip", mtime=t)
    _touch(art / "z.zip", mtime=t + 1)
    scanned, _ = scan_runtime_artifacts(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        include_html=False,
    )
    paths = [str(c.path) for c in scanned]
    assert paths == sorted(paths)
    retained, deleted = classify_retention_candidates(scanned, retain_count=1, max_age_days=0.0, now=t + 1)
    assert [str(c.path) for c in retained] == [str(art / "z.zip")]
    assert [str(c.path) for c in deleted] == [str(art / "a.zip")]


def test_json_output_keys_stable(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    _touch(art / "only.zip", mtime=1_700_000_000.0)
    rep = run_retention_pass(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        retain_count=3,
        max_age_days=0.0,
        include_html=False,
        dry_run=True,
        now=1_700_000_000.0,
    )
    dumped = json.dumps(rep, sort_keys=True)
    parsed = json.loads(dumped)
    assert list(parsed.keys()) == sorted(parsed.keys())
    for k in (
        "deleted_files",
        "dry_run",
        "reclaimed_bytes",
        "retained_files",
        "scanned_files",
        "skipped_files",
        "total_bytes_after",
        "total_bytes_before",
        "warnings",
    ):
        assert k in parsed


def test_reclaimed_bytes_correctness(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    now = 1_700_000_000.0
    _touch(art / "big.zip", size=1000, mtime=now)
    _touch(art / "small.zip", size=10, mtime=now + 1)
    rep = run_retention_pass(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        retain_count=1,
        max_age_days=0.0,
        include_html=False,
        dry_run=False,
        now=now + 5,
    )
    assert rep["reclaimed_bytes"] == 1000
    assert rep["total_bytes_after"] == 10


def test_strict_mode_on_warnings(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    rep = run_retention_pass(
        artifacts_dir=art / "missing",
        baselines_dir=None,
        reports_dir=None,
        retain_count=1,
        max_age_days=0.0,
        include_html=False,
        dry_run=True,
        now=1_700_000_000.0,
    )
    assert strict_exit_code(rep, strict=False) == 0
    assert strict_exit_code(rep, strict=True) == 1


def test_mixed_artifact_types(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    now = 1_700_000_000.0
    _touch(art / "runtime_bundle.zip", mtime=now)
    _touch(art / "regression.json", mtime=now + 1)
    _touch(art / "release_qualification.json", mtime=now + 2)
    _touch(art / "noise.txt", mtime=now + 3)
    scanned, _ = scan_runtime_artifacts(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        include_html=False,
    )
    names = {c.path.name for c in scanned}
    assert names == {"regression.json", "release_qualification.json", "runtime_bundle.zip"}
    assert "noise.txt" not in names


def test_directories_untouched(tmp_path: Path) -> None:
    art = tmp_path / "artifacts"
    art.mkdir()
    sub = art / "nested"
    sub.mkdir()
    (sub / "inner.zip").write_bytes(b"yz")
    _touch(art / "top.zip", mtime=1_700_000_000.0)
    rep = run_retention_pass(
        artifacts_dir=art,
        baselines_dir=None,
        reports_dir=None,
        retain_count=5,
        max_age_days=0.0,
        include_html=False,
        dry_run=False,
        now=1_700_000_000.0,
    )
    assert (sub / "inner.zip").is_file()
    skipped, _ = scan_skipped_entries(artifacts_dir=art, baselines_dir=None, reports_dir=None)
    assert any("directory:" in s for s in skipped)
    assert len(rep["scanned_files"]) == 1


def test_per_root_independent_retention(tmp_path: Path) -> None:
    art = tmp_path / "a"
    base = tmp_path / "b"
    art.mkdir()
    base.mkdir()
    now = 1_700_000_000.0
    for i in range(3):
        _touch(art / f"x{i}.zip", mtime=now + i)
        _touch(base / f"y{i}.zip", mtime=now + i)
    rep = run_retention_pass(
        artifacts_dir=art,
        baselines_dir=base,
        reports_dir=None,
        retain_count=2,
        max_age_days=0.0,
        include_html=False,
        dry_run=False,
        now=now + 10,
    )
    assert len(rep["deleted_files"]) == 2
    assert len(rep["retained_files"]) == 4


def test_apply_retention_policy_injected_unlink(tmp_path: Path) -> None:
    deleted: list[Path] = []

    def _unlink(p: Path) -> None:
        deleted.append(p)

    art = tmp_path / "artifacts"
    art.mkdir()
    now = 1_700_000_000.0
    _touch(art / "a.zip", mtime=now)
    c = FileCandidate(path=art / "a.zip", root_kind="artifacts", mtime=now, size_bytes=5)
    paths, warns = apply_retention_policy([c], dry_run=False, unlink=_unlink)
    assert paths == [str(art / "a.zip")]
    assert not warns
    assert (art / "a.zip").is_file()
    assert deleted == [art / "a.zip"]


def test_render_retention_summary_contains_dry_run() -> None:
    txt = render_retention_summary(
        {
            "deleted_files": [],
            "dry_run": False,
            "reclaimed_bytes": 0,
            "retained_files": [],
            "scanned_files": [],
            "skipped_files": [],
            "total_bytes_after": 0,
            "total_bytes_before": 0,
            "warnings": [],
        },
    )
    assert "Runtime retention summary" in txt
    assert "Dry-run: false" in txt


def test_snapshot_retention_max_count(tmp_path: Path) -> None:
    d = tmp_path / "ret"
    d.mkdir()
    s = minimal_test_settings(
        runtime_state_dir=str(d),
        runtime_snapshots_max_count=3,
        runtime_snapshots_max_age_hours=999,
        runtime_snapshots_max_storage_bytes=50_000_000,
    )
    for i in range(5):
        p = d / f"snapshot_{i}_x.json"
        p.write_text(json.dumps({"schema_version": 2, "i": i}), encoding="utf-8")
        time.sleep(0.01)
    deleted = cleanup_old_runtime_snapshots(s)
    assert deleted >= 2
    remaining = list(d.glob("snapshot_*.json"))
    assert len(remaining) <= 3


def test_snapshot_retention_max_age(tmp_path: Path) -> None:
    d = tmp_path / "ret2"
    d.mkdir()
    s = minimal_test_settings(
        runtime_state_dir=str(d),
        runtime_snapshots_max_count=50,
        runtime_snapshots_max_age_hours=0,
        runtime_snapshots_max_storage_bytes=50_000_000,
    )
    old = d / "snapshot_old_y.json"
    old.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    t = time.time() - 7200
    os.utime(old, (t, t))
    cleanup_old_runtime_snapshots(s)
    assert not old.exists()
