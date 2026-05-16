from __future__ import annotations

import json
import zipfile
from pathlib import Path

from utils.runtime_bundle import BUNDLE_DIR_NAME
from utils.release_qualification import (
    CHECK_ORDER,
    evaluate_release_qualification,
    render_release_report,
)


def _stability(
    *,
    rss_bytes: float,
    oldest: float = 1.0,
    pending: int = 2,
    timeline_b: int = 100,
    mod_lat: float = 0.5,
) -> dict:
    return {
        "derived": {"avg_oldest_pending_age_sec_sampled_kinds": oldest},
        "editorial_analytics": {"avg_publish_attempts_ring": 1.0, "moderation_latency_avg_sec": mod_lat},
        "metrics_export": {
            "counters": {
                "openai_failures": 0,
                "publish_failures": 0,
                "telethon_reconnects": 0,
                "telegram_api_failures": 0,
            },
        },
        "queue_depth_by_kind": {"ai": 1, "ingest": pending, "publisher": 0},
        "rss_bytes": rss_bytes,
        "runtime_state_file_bytes": {
            "editorial_drift_snapshots.json": 10,
            "event_history.json": 50,
            "operational_timeline.json": timeline_b,
            "suppression_state.json": 200,
        },
    }


def _bounded_summary() -> dict:
    return {
        "bounded_state_report": {
            "drift_snapshots": 1,
            "event_history_events": 2,
            "suppression_entries": 3,
            "timeline_events": 4,
            "timeline_file_bytes": 100,
        },
    }


def _integrity_clean() -> dict:
    return {"event_history_issues": [], "suppression_issues": [], "timeline_issues": []}


def _manifest(*, missing_soak: bool = False) -> dict:
    miss = ["soak_report.json"] if missing_soak else []
    files = [
        "benchmark.json",
        "integrity.json",
        "manifest.json",
        "runtime_summary.json",
        "stability.json",
    ]
    return {"included_files": sorted(files), "missing_files": sorted(miss)}


def _soak_healthy() -> dict:
    return {"bounded_report": {"ok": True, "timeline_events": 0}, "warnings": []}


def _write_qual_zip(
    path: Path,
    stability: dict,
    *,
    integrity: dict | None = None,
    summary: dict | None = None,
    manifest: dict | None = None,
    soak: dict | None = None,
    corrupt_stability: bool = False,
    skip_files: frozenset[str] = frozenset(),
) -> None:
    integ = integrity if integrity is not None else _integrity_clean()
    summ = summary if summary is not None else _bounded_summary()
    man = manifest if manifest is not None else _manifest()
    raw_stab = "{" if corrupt_stability else json.dumps(stability, sort_keys=True)
    with zipfile.ZipFile(path, "w") as zf:
        pairs = {
            "benchmark.json": json.dumps(stability, sort_keys=True).encode("utf-8"),
            "integrity.json": json.dumps(integ, sort_keys=True).encode("utf-8"),
            "manifest.json": json.dumps(man, sort_keys=True).encode("utf-8"),
            "runtime_summary.json": json.dumps(summ, sort_keys=True).encode("utf-8"),
            "stability.json": raw_stab.encode("utf-8"),
        }
        if soak is not None:
            pairs["soak_report.json"] = json.dumps(soak, sort_keys=True).encode("utf-8")
        for name, data in sorted(pairs.items()):
            if name in skip_files:
                continue
            zf.writestr(f"{BUNDLE_DIR_NAME}/{name}", data)


def test_successful_qualification(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    _write_qual_zip(b, st, soak=_soak_healthy())
    _write_qual_zip(c, st, soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=False,
        strict=True,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["qualification_status"] == "OK"
    assert res["release_ready"] is True
    assert code == 0


def test_regression_fail(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    _write_qual_zip(b, _stability(rss_bytes=10_000_000.0), soak=_soak_healthy())
    _write_qual_zip(c, _stability(rss_bytes=25_000_000.0), soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=10.0,
        fail_pct=50.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["regression"]["status"] == "FAIL"
    assert res["qualification_status"] == "FAIL"
    assert res["release_ready"] is False
    assert code == 1


def test_regression_warning_allowed(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    _write_qual_zip(b, _stability(rss_bytes=100.0, timeline_b=100), soak=_soak_healthy())
    _write_qual_zip(c, _stability(rss_bytes=100.0, timeline_b=118), soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=80.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["regression"]["status"] == "WARNING"
    assert res["qualification_status"] == "WARNING"
    assert res["release_ready"] is True
    assert code == 0


def test_regression_warning_denied(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    _write_qual_zip(b, _stability(rss_bytes=100.0, timeline_b=100), soak=_soak_healthy())
    _write_qual_zip(c, _stability(rss_bytes=100.0, timeline_b=118), soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=80.0,
        allow_warning=False,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["regression"]["status"] == "WARNING"
    assert res["release_ready"] is False
    assert code == 1


def test_require_regression_ok_blocks_warning_even_when_allowed(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    _write_qual_zip(b, _stability(rss_bytes=100.0, timeline_b=100), soak=_soak_healthy())
    _write_qual_zip(c, _stability(rss_bytes=100.0, timeline_b=118), soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=80.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=True,
    )
    assert res["checks"]["regression"]["status"] == "FAIL"
    assert res["release_ready"] is False
    assert code == 1


def test_missing_soak_optional_ok(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    _write_qual_zip(b, st, soak=None, skip_files=frozenset({"soak_report.json"}))
    _write_qual_zip(c, st, soak=None, skip_files=frozenset({"soak_report.json"}))
    res, _ = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=False,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["soak"]["status"] == "OK"
    assert res["checks"]["soak"]["detail"]["reason"] == "soak_report_absent"
    txt = render_release_report(res)
    assert "Soak: MISSING" in txt


def test_require_soak_missing_fails(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    _write_qual_zip(b, st, soak=_soak_healthy())
    _write_qual_zip(c, st, soak=None, skip_files=frozenset({"soak_report.json"}))
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=True,
        strict=False,
        require_soak=True,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["soak"]["status"] == "FAIL"
    assert res["release_ready"] is False
    assert code == 1


def test_integrity_issues_fail_when_required_clean(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    bad_integ = {"event_history_issues": ["x"], "suppression_issues": [], "timeline_issues": []}
    _write_qual_zip(b, st, soak=_soak_healthy())
    _write_qual_zip(c, st, integrity=bad_integ, soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["integrity"]["status"] == "FAIL"
    assert res["release_ready"] is False
    assert code == 1


def test_integrity_issues_warning_when_not_required_clean(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    bad_integ = {"event_history_issues": ["x"], "suppression_issues": [], "timeline_issues": []}
    _write_qual_zip(b, st, soak=_soak_healthy())
    _write_qual_zip(c, st, integrity=bad_integ, soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=False,
        require_regression_ok=False,
    )
    assert res["checks"]["integrity"]["status"] == "WARNING"
    assert res["qualification_status"] == "WARNING"
    assert res["release_ready"] is True
    assert code == 0


def test_corrupt_runtime_bundle(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    _write_qual_zip(b, st, soak=_soak_healthy())
    c.write_bytes(b"not a zip")
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["bundle_load"]["status"] == "FAIL"
    assert res["release_ready"] is False
    assert code == 1


def test_corrupt_json_in_bundle(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    _write_qual_zip(b, st, soak=_soak_healthy())
    _write_qual_zip(c, st, corrupt_stability=True, soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["bundle_load"]["status"] == "FAIL"
    assert any("invalid_json" in w for w in res["checks"]["bundle_load"]["detail"]["current_fatal"])
    assert code == 1


def test_deterministic_checks_and_json_keys(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    _write_qual_zip(b, st, soak=_soak_healthy())
    _write_qual_zip(c, st, soak=_soak_healthy())
    res, _ = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=False,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert list(res["checks"]) == list(CHECK_ORDER)
    dumped = json.dumps(res, sort_keys=True)
    parsed = json.loads(dumped)
    assert list(parsed["checks"]) == list(CHECK_ORDER)
    assert parsed["warnings"] == sorted(parsed["warnings"])
    assert parsed["failures"] == sorted(parsed["failures"])
    for k in (
        "baseline_bundle",
        "checks",
        "evaluated_at",
        "failures",
        "qualification_status",
        "release_ready",
        "runtime_bundle",
        "threshold_config",
        "warnings",
    ):
        assert k in parsed


def test_strict_mode_nonzero_on_warning(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    _write_qual_zip(b, _stability(rss_bytes=100.0, timeline_b=100), soak=_soak_healthy())
    _write_qual_zip(c, _stability(rss_bytes=100.0, timeline_b=118), soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=80.0,
        allow_warning=True,
        strict=True,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["qualification_status"] == "WARNING"
    assert res["release_ready"] is True
    assert code == 1


def test_soak_unhealthy_fails(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    bad_soak = {"bounded_report": {"ok": False}, "warnings": ["nope"]}
    _write_qual_zip(b, st, soak=_soak_healthy())
    _write_qual_zip(c, st, soak=bad_soak)
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["soak"]["status"] == "FAIL"
    assert res["release_ready"] is False
    assert code == 1


def test_queue_health_fail_propagates(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    low = _stability(rss_bytes=10_000_000.0, oldest=1.0, pending=1)
    high = _stability(rss_bytes=10_000_000.0, oldest=500.0, pending=500)
    _write_qual_zip(b, low, soak=_soak_healthy())
    _write_qual_zip(c, high, soak=_soak_healthy())
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=5.0,
        fail_pct=15.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=True,
        require_regression_ok=False,
    )
    assert res["checks"]["queue_health"]["status"] == "FAIL"
    assert res["release_ready"] is False
    assert code == 1


def test_missing_soft_files_warns(tmp_path: Path) -> None:
    """Minimal zip (regression-style) lacks recommended bundle members."""
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    st = _stability(rss_bytes=10_000_000.0)
    with zipfile.ZipFile(b, "w") as zf:
        zf.writestr(f"{BUNDLE_DIR_NAME}/stability.json", json.dumps(st, sort_keys=True).encode("utf-8"))
        zf.writestr(f"{BUNDLE_DIR_NAME}/benchmark.json", json.dumps(st, sort_keys=True).encode("utf-8"))
    with zipfile.ZipFile(c, "w") as zf:
        zf.writestr(f"{BUNDLE_DIR_NAME}/stability.json", json.dumps(st, sort_keys=True).encode("utf-8"))
        zf.writestr(f"{BUNDLE_DIR_NAME}/benchmark.json", json.dumps(st, sort_keys=True).encode("utf-8"))
    res, code = evaluate_release_qualification(
        c,
        b,
        warn_pct=15.0,
        fail_pct=50.0,
        allow_warning=True,
        strict=False,
        require_soak=False,
        require_integrity_clean=False,
        require_regression_ok=False,
    )
    assert res["checks"]["bundle_load"]["status"] == "WARNING"
    assert "missing_recommended" in json.dumps(res["checks"]["bundle_load"]["detail"])
