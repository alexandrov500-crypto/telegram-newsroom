"""Advisory tools: bounded output, read-only, explainable."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.drift_forecast import build_drift_forecast
from tools.maintenance_forecast import build_forecast
from tools.maintenance_recommendations import build_recommendations
from utils.operational_intel_context import build_intel_context
from utils.operational_trends import TrendSample, analyze_trends

REPO = Path(__file__).resolve().parents[2]


def _ctx_with_history(tmp_path: Path) -> dict:
    hist = tmp_path / "history"
    hist.mkdir()
    samples = [
        TrendSample(captured_at="2026-05-01T00:00:00Z", evidence_dir_bytes=50_000_000).to_dict(),
        TrendSample(captured_at="2026-05-10T00:00:00Z", evidence_dir_bytes=120_000_000).to_dict(),
    ]
    (hist / "a.json").write_text(json.dumps(samples), encoding="utf-8")
    od = tmp_path / "out"
    od.mkdir()
    (od / "runtime").mkdir()
    return build_intel_context(output_dir=od, history_dir=hist)


def test_forecast_advisory_only(tmp_path: Path) -> None:
    fc = build_forecast(_ctx_with_history(tmp_path))
    assert fc["advisory_only"] is True
    assert len(fc["forecasts"]) <= 12


def test_drift_forecast_bounded_scores(tmp_path: Path) -> None:
    df = build_drift_forecast(_ctx_with_history(tmp_path))
    for risk in (df.get("risks") or {}).values():
        assert 0 <= risk["score"] <= 100
        assert risk["level"] in ("low", "medium", "high")


def test_recommendations_capped(tmp_path: Path) -> None:
    rec = build_recommendations(_ctx_with_history(tmp_path))
    assert len(rec["daily"]) <= 5
    assert len(rec["weekly"]) <= 8
    assert rec["advisory_only"] is True


def test_ops_summary_cli(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setenv("OPS_HISTORY_DIR", str(tmp_path / "history"))
    _ctx_with_history(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/ops_summary.py"), "--json"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["read_only"] is True


def test_tools_no_default_file_mutation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))
    subprocess.run(
        [sys.executable, str(REPO / "tools/maintenance_forecast.py")],
        cwd=str(REPO),
        capture_output=True,
        timeout=60,
    )
    after = set(tmp_path.rglob("*"))
    assert before == after


def test_explainable_trend_confidence() -> None:
    r = analyze_trends(
        [
            TrendSample(captured_at="2026-05-01T00:00:00Z"),
            TrendSample(captured_at="2026-05-02T00:00:00Z"),
        ]
    )
    assert r["confidence"] in ("low", "medium", "high")
