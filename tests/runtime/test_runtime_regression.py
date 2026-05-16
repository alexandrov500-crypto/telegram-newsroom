from __future__ import annotations

import json
import zipfile
from pathlib import Path

from utils.runtime_bundle import BUNDLE_DIR_NAME
from utils.runtime_regression import (
    METRIC_LABELS,
    METRIC_ORDER,
    build_comparison_json,
    compare_runtime_metrics,
    extract_regression_metrics,
    load_runtime_bundle,
    render_regression_report,
    run_regression_comparison,
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


def _write_bundle(path: Path, stability: dict, *, corrupt_stability: bool = False) -> None:
    raw = "{" if corrupt_stability else json.dumps(stability, sort_keys=True)
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{BUNDLE_DIR_NAME}/stability.json", raw.encode("utf-8"))
        zf.writestr(f"{BUNDLE_DIR_NAME}/benchmark.json", json.dumps(stability, sort_keys=True).encode("utf-8"))


def test_identical_bundles_ok(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    p = _stability(rss_bytes=10_000_000.0)
    _write_bundle(b, p)
    _write_bundle(c, p)
    payload, code = run_regression_comparison(b, c, warn_pct=15.0, fail_pct=50.0)
    assert payload["overall_status"] == "OK"
    assert code == 0


def test_regression_fail_on_rss(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    _write_bundle(b, _stability(rss_bytes=10_000_000.0))
    _write_bundle(c, _stability(rss_bytes=25_000_000.0))
    payload, code = run_regression_comparison(b, c, warn_pct=10.0, fail_pct=50.0)
    assert payload["overall_status"] == "FAIL"
    assert code == 1
    row = next(x for x in payload["metrics"] if x["metric"] == "rss_mb")
    assert row["status"] == "FAIL"


def test_warning_threshold(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    _write_bundle(b, _stability(rss_bytes=100.0, timeline_b=100))
    _write_bundle(c, _stability(rss_bytes=100.0, timeline_b=118))
    payload, code = run_regression_comparison(b, c, warn_pct=15.0, fail_pct=80.0)
    tl = next(x for x in payload["metrics"] if x["metric"] == "timeline_bytes")
    assert tl["status"] == "WARNING"
    assert code == 0


def test_ignore_missing(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    half = _stability(rss_bytes=10.0)
    del half["metrics_export"]
    _write_bundle(b, half)
    _write_bundle(c, _stability(rss_bytes=10.0))
    payload_ok, _ = run_regression_comparison(b, c, ignore_missing=True)
    assert payload_ok["overall_status"] == "OK"


def test_strict_with_bundle_warnings(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    _write_bundle(b, _stability(rss_bytes=10.0), corrupt_stability=True)
    _write_bundle(c, _stability(rss_bytes=10.0))
    _code_strict = run_regression_comparison(b, c, strict=True)[1]
    assert _code_strict == 1
    _code_loose = run_regression_comparison(b, c, strict=False)[1]
    assert _code_loose == 0


def test_bad_zip_path(tmp_path: Path) -> None:
    p = tmp_path / "not.zip"
    p.write_text("not a zip", encoding="utf-8")
    payload, code = run_regression_comparison(p, p)
    assert len(payload["warnings"]) > 0


def test_deterministic_metric_order_report(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    p = _stability(rss_bytes=1.0)
    _write_bundle(b, p)
    _write_bundle(c, p)
    payload, _ = run_regression_comparison(b, c)
    txt = render_regression_report(
        list(payload["metrics"]),
        "OK",
        baseline_label="b",
        current_label="c",
    )
    idx = [txt.find(METRIC_LABELS[m]) for m in METRIC_ORDER]
    assert idx == sorted(idx)


def test_json_output_shape(tmp_path: Path) -> None:
    b = tmp_path / "b.zip"
    c = tmp_path / "c.zip"
    p = _stability(rss_bytes=1.0)
    _write_bundle(b, p)
    _write_bundle(c, p)
    payload, _ = run_regression_comparison(b, c)
    j = build_comparison_json(
        baseline_path="b",
        current_path="c",
        rows=list(payload["metrics"]),
        bundle_warnings=list(payload["warnings"]),
        overall="OK",
        warn_pct=1.0,
        fail_pct=2.0,
        strict=False,
        ignore_missing=False,
    )
    assert list(j.keys()) == sorted(j.keys())
    assert "metrics" in j


def test_compare_missing_metrics_rows(tmp_path: Path) -> None:
    base_m = extract_regression_metrics({"stability.json": _stability(rss_bytes=1_000_000.0)})
    cur_m = extract_regression_metrics({})
    rows, rw, overall = compare_runtime_metrics(cur_m, base_m, warn_pct=10.0, fail_pct=50.0, ignore_missing=False)
    assert overall == "WARNING"
    assert rw


def test_compare_regression_skip_metrics_respects_frozenset() -> None:
    base_m = extract_regression_metrics({"stability.json": _stability(rss_bytes=100.0, timeline_b=0)})
    cur_m = extract_regression_metrics({"stability.json": _stability(rss_bytes=100.0, timeline_b=10_000)})
    rows, _rw, overall = compare_runtime_metrics(
        cur_m,
        base_m,
        warn_pct=15.0,
        fail_pct=50.0,
        ignore_missing=True,
        regression_skip_metrics=frozenset({"timeline_bytes"}),
    )
    assert overall == "OK"
    by_metric = {r["metric"]: r for r in rows}
    assert by_metric["timeline_bytes"]["status"] == "OK"
    assert "regression_skipped:configured" in (by_metric["timeline_bytes"].get("notes") or [])


def test_load_corrupt_json_warning(tmp_path: Path) -> None:
    z = tmp_path / "z.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr(f"{BUNDLE_DIR_NAME}/stability.json", b"{")
    data, warns = load_runtime_bundle(z)
    assert warns
    assert any("stability.json" in w for w in warns)
