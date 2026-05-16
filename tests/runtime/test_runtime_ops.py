from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from tests.conftest import minimal_test_settings
from utils import runtime_ops as ro
from utils.runtime_ops import (
    RuntimeOpsContext,
    StepResult,
    ops_exit_code,
    render_runtime_ops_summary,
    run_nightly_check,
    run_single_command,
)


def _ctx(tmp_path: Path, **kw: object) -> RuntimeOpsContext:
    base = {
        "output_dir": tmp_path / "out",
        "runtime_dir": tmp_path / "rt",
        "settings_factory": lambda: minimal_test_settings(runtime_state_dir=str(tmp_path / "rt")),
    }
    base.update(kw)
    return RuntimeOpsContext(**base)  # type: ignore[arg-type]


def _minimal_runtime_dir(rd: Path) -> None:
    rd.mkdir(parents=True, exist_ok=True)
    (rd / "soak_report.json").write_text('{"profile": "low"}', encoding="utf-8")
    (rd / "queue_pressure.json").write_text("{}", encoding="utf-8")


def test_preflight_command_ok(tmp_path: Path) -> None:
    rd = tmp_path / "rt"
    rd.mkdir()
    ctx = _ctx(tmp_path, runtime_dir=rd)
    rep = run_single_command("preflight", ctx)
    assert rep["command"] == "preflight"
    assert rep["ok"] is True
    assert rep["status"] == "OK"
    assert rep["executed_steps"] == ["preflight"]
    assert rep["skipped_steps"] == []
    keys = {
        "command",
        "completed_at",
        "executed_steps",
        "generated_artifacts",
        "ok",
        "skipped_steps",
        "started_at",
        "status",
        "steps",
        "warnings",
    }
    assert keys.issubset(rep.keys())


def test_nightly_check_step_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    out = tmp_path / "out"
    ctx = _ctx(tmp_path, runtime_dir=rd, output_dir=out, short_soak=True)

    def _fast_benchmark(c: RuntimeOpsContext) -> StepResult:
        p = c.output_dir / "ops_benchmark.json"
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p.write_text('{"stub": true}', encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    def _fast_soak(c: RuntimeOpsContext) -> StepResult:
        p = c.runtime_dir / "soak_report.json" if c.runtime_dir else None
        assert p is not None
        return StepResult("soak", "OK", 0, artifacts=[str(p)])

    monkeypatch.setattr(ro, "run_benchmark_step", _fast_benchmark)
    monkeypatch.setattr(ro, "run_soak_step", _fast_soak)

    rep = run_nightly_check(ctx)
    names = [s["name"] for s in rep["steps"]]
    assert names == list(ro.NIGHTLY_STEP_ORDER)
    skipped = set(rep["skipped_steps"])
    assert rep["executed_steps"] == [n for n in ro.NIGHTLY_STEP_ORDER if n not in skipped]
    assert "regression:missing_baseline_or_bundle" in rep["warnings"]


def test_dry_run_skips_side_effects(tmp_path: Path) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd, dry_run=True)
    rep = run_nightly_check(ctx)
    skipped = set(rep["skipped_steps"])
    assert {"benchmark", "soak", "bundle", "regression", "qualification", "dashboard", "retention"}.issubset(skipped)
    assert rep["executed_steps"] == ["preflight"]


def test_skip_retention(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd, skip_retention=True, short_soak=True)

    def _fast_benchmark(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    def _fast_soak(c: RuntimeOpsContext) -> StepResult:
        p = c.runtime_dir / "soak_report.json"
        assert p is not None
        return StepResult("soak", "OK", 0, artifacts=[str(p)])

    monkeypatch.setattr(ro, "run_benchmark_step", _fast_benchmark)
    monkeypatch.setattr(ro, "run_soak_step", _fast_soak)

    rep = run_nightly_check(ctx)
    assert "retention" in rep["skipped_steps"]
    assert any(s["name"] == "retention" and s["status"] == "SKIPPED" for s in rep["steps"])


def test_strict_fails_on_warning_step(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd, strict=True, short_soak=True)

    def _fast_benchmark(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    def _fast_soak(c: RuntimeOpsContext) -> StepResult:
        p = c.runtime_dir / "soak_report.json"
        assert p is not None
        return StepResult("soak", "OK", 0, artifacts=[str(p)])

    def _warn_regression(c: RuntimeOpsContext) -> StepResult:
        return StepResult("regression", "WARNING", 0, warnings=["regression:warn"])

    monkeypatch.setattr(ro, "run_benchmark_step", _fast_benchmark)
    monkeypatch.setattr(ro, "run_soak_step", _fast_soak)
    monkeypatch.setattr(ro, "run_regression_step", _warn_regression)

    rep = run_nightly_check(ctx)
    assert rep["ok"] is False
    assert ops_exit_code(rep, strict=True) == 1


def test_failed_step_marks_nightly_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd, short_soak=True)

    def _fast_benchmark(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    def _fast_soak(c: RuntimeOpsContext) -> StepResult:
        p = c.runtime_dir / "soak_report.json"
        assert p is not None
        return StepResult("soak", "OK", 0, artifacts=[str(p)])

    def _fail_bundle(_c: RuntimeOpsContext) -> StepResult:
        return StepResult("bundle", "FAIL", 1, warnings=["bundle:boom"])

    monkeypatch.setattr(ro, "run_benchmark_step", _fast_benchmark)
    monkeypatch.setattr(ro, "run_soak_step", _fast_soak)
    monkeypatch.setattr(ro, "run_bundle_step", _fail_bundle)

    rep = run_nightly_check(ctx)
    assert rep["status"] == "FAIL"
    assert rep["ok"] is False
    assert ops_exit_code(rep, strict=False) == 1


def test_warning_propagation_aggregate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd, strict=False, short_soak=True)

    def _stub_bench(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    def _fast_soak(c: RuntimeOpsContext) -> StepResult:
        p = c.runtime_dir / "soak_report.json"
        assert p is not None
        return StepResult("soak", "OK", 0, artifacts=[str(p)])

    def _warn_reg(_c: RuntimeOpsContext) -> StepResult:
        return StepResult("regression", "WARNING", 0, warnings=["w1"])

    monkeypatch.setattr(ro, "run_benchmark_step", _stub_bench)
    monkeypatch.setattr(ro, "run_soak_step", _fast_soak)
    monkeypatch.setattr(ro, "run_regression_step", _warn_reg)

    rep = run_nightly_check(ctx)
    assert "w1" in rep["warnings"]
    assert rep["status"] == "WARNING"
    assert rep["ok"] is True


def test_generated_artifacts_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    od = tmp_path / "out"
    ctx = _ctx(tmp_path, runtime_dir=rd, output_dir=od, short_soak=True)

    def _stub_bench(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    monkeypatch.setattr(ro, "run_benchmark_step", _stub_bench)

    rep = run_nightly_check(ctx)
    arts = rep["generated_artifacts"]
    assert arts == sorted(arts)
    assert any("ops_benchmark.json" in a for a in arts)
    assert any(str(od / "runtime_bundle.zip") in a for a in arts)


def test_json_shape_stable_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd, short_soak=True)

    def _stub_bench(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    monkeypatch.setattr(ro, "run_benchmark_step", _stub_bench)

    rep = run_nightly_check(ctx)
    blob = json.dumps(rep, sort_keys=True)
    parsed = json.loads(blob)
    required = (
        "command",
        "completed_at",
        "executed_steps",
        "generated_artifacts",
        "skipped_steps",
        "started_at",
        "status",
        "steps",
        "warnings",
    )
    for k in required:
        assert k in parsed


def test_graceful_skipped_regression_without_baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd, baseline=None, short_soak=True)

    def _stub_bench(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    monkeypatch.setattr(ro, "run_benchmark_step", _stub_bench)

    rep = run_nightly_check(ctx)
    reg = next(s for s in rep["steps"] if s["name"] == "regression")
    assert reg["status"] == "SKIPPED"


def test_partial_single_bundle(tmp_path: Path) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd)
    rep = run_single_command("bundle", ctx)
    assert rep["ok"] is True
    assert any("runtime_bundle.zip" in a for a in rep["generated_artifacts"])


def test_render_summary_lines(tmp_path: Path) -> None:
    rd = tmp_path / "rt"
    rd.mkdir()
    rep = run_single_command("preflight", _ctx(tmp_path, runtime_dir=rd))
    txt = render_runtime_ops_summary(rep)
    assert "Runtime ops summary" in txt
    assert "[OK] preflight" in txt
    assert "Overall: OK" in txt


def test_ops_exit_code_strict_requires_aggregate_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)
    ctx = _ctx(tmp_path, runtime_dir=rd, short_soak=True, strict=False)

    def _stub_bench(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    def _fast_soak(c: RuntimeOpsContext) -> StepResult:
        p = c.runtime_dir / "soak_report.json"
        assert p is not None
        return StepResult("soak", "OK", 0, artifacts=[str(p)])

    def _warn_reg(_c: RuntimeOpsContext) -> StepResult:
        return StepResult("regression", "WARNING", 0, warnings=["w"])

    monkeypatch.setattr(ro, "run_benchmark_step", _stub_bench)
    monkeypatch.setattr(ro, "run_soak_step", _fast_soak)
    monkeypatch.setattr(ro, "run_regression_step", _warn_reg)

    rep = run_nightly_check(ctx)
    assert rep["ok"] is True
    assert rep["status"] == "WARNING"
    assert ops_exit_code(rep, strict=False) == 0
    assert ops_exit_code(rep, strict=True) == 1


def test_cli_main_json_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    rd = tmp_path / "rt"
    _minimal_runtime_dir(rd)

    def _stub_bench(c: RuntimeOpsContext) -> StepResult:
        c.output_dir.mkdir(parents=True, exist_ok=True)
        p = c.output_dir / "ops_benchmark.json"
        p.write_text("{}", encoding="utf-8")
        return StepResult("benchmark", "OK", 0, artifacts=[str(p)])

    def _fast_soak(c: RuntimeOpsContext) -> StepResult:
        p = c.runtime_dir / "soak_report.json"
        assert p is not None
        return StepResult("soak", "OK", 0, artifacts=[str(p)])

    monkeypatch.setattr(ro, "run_benchmark_step", _stub_bench)
    monkeypatch.setattr(ro, "run_soak_step", _fast_soak)
    monkeypatch.setattr(
        "app.config.load_settings",
        lambda: minimal_test_settings(runtime_state_dir=str(rd)),
    )

    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("runtime_ops_cli", repo / "tools" / "runtime_ops.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    argv = [
        "nightly-check",
        "--runtime-dir",
        str(rd),
        "--output-dir",
        str(tmp_path / "out"),
        "--short-soak",
        "--skip-retention",
        "--json-output",
    ]
    code = mod.main(argv)
    assert code == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["command"] == "nightly-check"
    assert "retention" in data["skipped_steps"]
