from __future__ import annotations

import json
import zipfile
from pathlib import Path

from utils.operational_dashboard import (
    build_dashboard_payload,
    extract_dashboard_sections,
    load_dashboard_inputs,
    render_dashboard_html,
    render_status_badge,
    strict_dashboard_exit_code,
)
from utils.runtime_bundle import BUNDLE_DIR_NAME


def _mini_bundle_zip(path: Path) -> None:
    manifest = {
        "artifact_sizes": {"benchmark.json": 10, "manifest.json": 20, "stability.json": 10},
        "bundle_version": "1",
        "generated_at": "2020-01-01T00:00:00Z",
        "git_sha": "abc123deadbeef",
        "included_files": sorted(["benchmark.json", "manifest.json", "stability.json"]),
        "missing_files": ["soak_report.json"],
    }
    stability = {
        "derived": {"avg_oldest_pending_age_sec_sampled_kinds": 1.2},
        "editorial_analytics": {"avg_publish_attempts_ring": 1.1, "moderation_latency_avg_sec": 0.4},
        "metrics_export": {"counters": {"telethon_reconnects": 0}},
        "queue_depth_by_kind": {"ingest": 2},
        "rss_bytes": 1e6,
    }
    summary = {"bounded_state_report": {"timeline_events": 3, "timeline_file_bytes": 99}}
    with zipfile.ZipFile(path, "w") as zf:
        for name, obj in (
            ("benchmark.json", stability),
            ("manifest.json", manifest),
            ("runtime_summary.json", summary),
            ("stability.json", stability),
        ):
            zf.writestr(
                f"{BUNDLE_DIR_NAME}/{name}",
                json.dumps(obj, sort_keys=True).encode("utf-8"),
            )


def test_successful_dashboard_generation(tmp_path: Path) -> None:
    z = tmp_path / "b.zip"
    _mini_bundle_zip(z)
    qual = tmp_path / "q.json"
    qual.write_text(
        json.dumps(
            {
                "baseline_bundle": "/b.zip",
                "checks": {
                    "integrity": {"detail": {}, "status": "OK"},
                    "regression": {"detail": {"overall": "OK"}, "status": "OK"},
                },
                "failures": [],
                "qualification_status": "OK",
                "release_ready": True,
                "warnings": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    reg = tmp_path / "r.json"
    reg.write_text(
        json.dumps(
            {
                "baseline_bundle": "/b.zip",
                "current_bundle": "/c.zip",
                "metrics": [
                    {
                        "baseline": 1.0,
                        "current": 1.0,
                        "metric": "rss_mb",
                        "notes": [],
                        "pct_change": 0.0,
                        "status": "OK",
                    },
                ],
                "overall_status": "OK",
                "warnings": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    ret = tmp_path / "t.json"
    ret.write_text(
        json.dumps(
            {
                "deleted_files": ["a.zip"],
                "dry_run": False,
                "reclaimed_bytes": 10,
                "retained_files": ["b.zip"],
                "scanned_files": ["a.zip", "b.zip"],
                "skipped_files": [],
                "total_bytes_after": 100,
                "total_bytes_before": 110,
                "warnings": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    payload = build_dashboard_payload(
        runtime_bundle=z,
        qualification_report=qual,
        regression_report=reg,
        retention_report=ret,
        title="T",
    )
    html = render_dashboard_html(payload, include_json_snippets=False)
    assert "<h1>T</h1>" in html
    assert "id=\"overview\"" in html
    assert "abc123deadbeef" in html
    assert "id=\"regression_summary\"" in html
    assert "id=\"retention\"" in html
    assert "raw-json" not in html


def test_missing_sections_graceful(tmp_path: Path) -> None:
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=None,
        regression_report=None,
        retention_report=None,
        title="Empty",
    )
    html = render_dashboard_html(payload, include_json_snippets=False)
    assert "id=\"overview\"" in html
    assert "No regression report" in html or "n/a" in html


def test_corrupt_json_handling(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=bad,
        regression_report=None,
        retention_report=None,
        title="X",
    )
    assert any("invalid_json" in w for w in payload["input_warnings"])
    assert strict_dashboard_exit_code(payload, strict=True) == 1


def test_deterministic_html_section_ordering(tmp_path: Path) -> None:
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=None,
        regression_report=None,
        retention_report=None,
        title="Ord",
    )
    html = render_dashboard_html(payload, include_json_snippets=False)
    ids = ["overview", "runtime_summary", "regression_summary", "qualification", "retention", "artifacts", "input_warnings"]
    pos = [html.index(f'id="{i}"') for i in ids]
    assert pos == sorted(pos)


def test_include_json_snippets_behavior(tmp_path: Path) -> None:
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=None,
        regression_report=None,
        retention_report=None,
        title="Snip",
    )
    on = render_dashboard_html(payload, include_json_snippets=True)
    off = render_dashboard_html(payload, include_json_snippets=False)
    assert 'id="raw-json"' in on
    assert 'id="raw-json"' not in off


def test_status_badge_rendering() -> None:
    assert "badge-ok" in render_status_badge("OK")
    assert "badge-warn" in render_status_badge("WARNING")
    assert "badge-fail" in render_status_badge("FAIL")
    assert "UNKNOWN" in render_status_badge("weird")


def test_self_contained_html_no_external_assets(tmp_path: Path) -> None:
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=None,
        regression_report=None,
        retention_report=None,
        title="Local",
    )
    html = render_dashboard_html(payload, include_json_snippets=True).lower()
    assert "https://" not in html
    assert "http://" not in html
    assert "<script" not in html


def test_missing_artifact_bundle(tmp_path: Path) -> None:
    missing = tmp_path / "nope.zip"
    payload = build_dashboard_payload(
        runtime_bundle=missing,
        qualification_report=None,
        regression_report=None,
        retention_report=None,
        title="M",
    )
    assert any("bundle:" in w for w in payload["input_warnings"])


def test_release_ready_rendering(tmp_path: Path) -> None:
    qual = tmp_path / "q.json"
    qual.write_text(
        json.dumps({"qualification_status": "WARNING", "release_ready": False}, sort_keys=True),
        encoding="utf-8",
    )
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=qual,
        regression_report=None,
        retention_report=None,
        title="R",
    )
    html = render_dashboard_html(payload, include_json_snippets=False)
    assert "false" in html
    assert "badge-warn" in html


def test_regression_rendering(tmp_path: Path) -> None:
    reg = tmp_path / "r.json"
    reg.write_text(
        json.dumps(
            {
                "metrics": [
                    {
                        "baseline": 1,
                        "current": 2,
                        "metric": "rss_mb",
                        "notes": [],
                        "pct_change": 100.0,
                        "status": "FAIL",
                    },
                ],
                "overall_status": "FAIL",
                "warnings": [],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=None,
        regression_report=reg,
        retention_report=None,
        title="Reg",
    )
    html = render_dashboard_html(payload, include_json_snippets=False)
    assert "badge-fail" in html
    assert "Top regressions" in html


def test_retention_rendering(tmp_path: Path) -> None:
    ret = tmp_path / "t.json"
    ret.write_text(
        json.dumps({"reclaimed_bytes": 42, "scanned_files": ["a"], "deleted_files": [], "retained_files": ["a"], "dry_run": True}),
        encoding="utf-8",
    )
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=None,
        regression_report=None,
        retention_report=ret,
        title="Ret",
    )
    html = render_dashboard_html(payload, include_json_snippets=False)
    assert "reclaimed_bytes" in html
    assert "42" in html


def test_strict_mode_behavior(tmp_path: Path) -> None:
    bad = tmp_path / "x.json"
    bad.write_text("notjson", encoding="utf-8")
    payload = build_dashboard_payload(
        runtime_bundle=None,
        qualification_report=bad,
        regression_report=None,
        retention_report=None,
        title="S",
    )
    assert strict_dashboard_exit_code(payload, strict=False) == 0
    assert strict_dashboard_exit_code(payload, strict=True) == 1


def test_load_and_extract_deterministic(tmp_path: Path) -> None:
    z = tmp_path / "b.zip"
    _mini_bundle_zip(z)
    inp = load_dashboard_inputs(
        runtime_bundle=z,
        qualification_report=None,
        regression_report=None,
        retention_report=None,
    )
    secs = extract_dashboard_sections(inp)
    assert [s[0] for s in secs] == [
        "overview",
        "runtime_summary",
        "regression_summary",
        "qualification",
        "retention",
        "artifacts",
        "input_warnings",
    ]
