from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from tests.conftest import minimal_test_settings
from utils.runtime_preflight import (
    CHECK_ORDER,
    DISPLAY_LABELS,
    evaluate_preflight,
    render_preflight_report,
    render_status_line,
    run_filesystem_checks,
    run_redis_checks,
    strict_preflight_exit_code,
)


def _base_settings(tmp_path: Path, **kw):
    return minimal_test_settings(runtime_state_dir=str(tmp_path), **kw)


def test_successful_preflight(tmp_path: Path) -> None:
    s = _base_settings(tmp_path)
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=100.0,
    )
    assert rep["preflight_ok"] is True
    assert rep["checks"]["filesystem"]["status"] == "OK"
    assert rep["checks"]["redis"]["status"] == "SKIPPED"


def test_missing_directories_filesystem_fail(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    s = _base_settings(tmp_path)
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=missing,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    assert rep["checks"]["filesystem"]["status"] == "FAIL"
    assert rep["checks"]["artifacts"]["status"] == "WARNING"


@pytest.mark.skipif(os.name == "nt", reason="chmod semantics differ on Windows")
def test_unwritable_directory(tmp_path: Path) -> None:
    d = tmp_path / "ro"
    d.mkdir()
    os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)
    try:
        s = _base_settings(tmp_path)
        rep = evaluate_preflight(
            runtime_dir=d,
            artifacts_dir=None,
            reports_dir=None,
            settings=s,
            settings_load_error=None,
            check_redis=False,
            check_disk_space=False,
            min_free_mb=1.0,
        )
        assert rep["checks"]["filesystem"]["status"] == "FAIL"
    finally:
        os.chmod(d, stat.S_IRWXU)


def test_corrupt_runtime_json(tmp_path: Path) -> None:
    (tmp_path / "operational_timeline.json").write_text("{", encoding="utf-8")
    s = _base_settings(tmp_path)
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    assert rep["checks"]["runtime_state"]["status"] == "FAIL"


def test_settings_load_failure() -> None:
    rep = evaluate_preflight(
        runtime_dir=None,
        artifacts_dir=None,
        reports_dir=None,
        settings=None,
        settings_load_error="RuntimeError('missing env')",
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    assert rep["checks"]["settings"]["status"] == "FAIL"
    assert rep["preflight_ok"] is False


def test_sqlite_inaccessible(tmp_path: Path) -> None:
    s = _base_settings(tmp_path, database_url="sqlite+aiosqlite:////no/such/path/preflight_bad.sqlite3")
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    assert rep["checks"]["sqlite"]["status"] == "FAIL"


def test_disk_threshold_fail(tmp_path: Path) -> None:
    s = _base_settings(tmp_path)
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=True,
        min_free_mb=1e12,
    )
    assert rep["checks"]["disk"]["status"] == "FAIL"


def test_redis_skipped(tmp_path: Path) -> None:
    s = _base_settings(tmp_path)
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    assert rep["checks"]["redis"]["status"] == "SKIPPED"


def test_redis_check_mocked(tmp_path: Path) -> None:
    import sys
    from types import ModuleType

    fake_redis = ModuleType("redis")

    class _Redis:
        @staticmethod
        def from_url(*_a, **_k):
            class _C:
                def ping(self) -> bool:
                    return True

                def close(self) -> None:
                    return None

            return _C()

    fake_redis.Redis = _Redis
    sys.modules["redis"] = fake_redis
    try:
        s = minimal_test_settings(
            runtime_state_dir=str(tmp_path),
            redis_enabled=True,
            redis_url="redis://127.0.0.1:6379/0",
        )
        out = run_redis_checks(s, check_redis=True)
        assert out["status"] == "OK"
    finally:
        sys.modules.pop("redis", None)


def test_deterministic_report_ordering(tmp_path: Path) -> None:
    s = _base_settings(tmp_path)
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    txt = render_preflight_report(rep)
    lines = [ln for ln in txt.splitlines() if ln.startswith("[")]
    labels_order = [ln.split("]", 1)[1].strip() for ln in lines[: len(CHECK_ORDER)]]
    assert labels_order == [DISPLAY_LABELS[k] for k in CHECK_ORDER]


def test_json_output_keys_sorted(tmp_path: Path) -> None:
    import json

    s = _base_settings(tmp_path)
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    dumped = json.dumps(rep, sort_keys=True)
    parsed = json.loads(dumped)
    assert list(parsed["checks"]) == sorted(parsed["checks"])


def test_strict_mode_behavior(tmp_path: Path) -> None:
    s = _base_settings(tmp_path)
    (tmp_path / "operational_timeline.json").write_text(
        json.dumps({"events": [], "version": 99}, sort_keys=True),
        encoding="utf-8",
    )
    rep = evaluate_preflight(
        runtime_dir=tmp_path,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    assert rep["checks"]["runtime_state"]["status"] == "WARNING"
    assert rep["overall_status"] == "WARNING"
    assert strict_preflight_exit_code(rep, strict=False) == 0
    assert strict_preflight_exit_code(rep, strict=True) == 1


def test_temp_file_cleanup(tmp_path: Path) -> None:
    fs = run_filesystem_checks(runtime_dir=tmp_path, artifacts_dir=None, reports_dir=None)
    assert fs["status"] == "OK"
    assert not list(tmp_path.glob("preflight_*"))


def test_status_badge_rendering() -> None:
    assert "[OK]" in render_status_line("X", "OK")
    assert "[SKIPPED]" in render_status_line("R", "SKIPPED")


def test_all_dirs_none_warning(tmp_path: Path) -> None:
    s = _base_settings(tmp_path)
    rep = evaluate_preflight(
        runtime_dir=None,
        artifacts_dir=None,
        reports_dir=None,
        settings=s,
        settings_load_error=None,
        check_redis=False,
        check_disk_space=False,
        min_free_mb=1.0,
    )
    assert any("no_directories_specified" in m for m in rep["checks"]["filesystem"]["messages"])
    assert rep["checks"]["filesystem"]["status"] == "WARNING"
