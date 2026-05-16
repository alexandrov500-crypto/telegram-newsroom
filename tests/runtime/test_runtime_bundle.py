from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tests.conftest import minimal_test_settings
from utils.runtime_bundle import (
    BUNDLE_DIR_NAME,
    collect_runtime_artifacts,
    write_runtime_bundle,
)


def _zip_names(zip_path: Path) -> set[str]:
    with zipfile.ZipFile(zip_path, "r") as zf:
        return set(zf.namelist())


def test_bundle_creation_success(tmp_path: Path) -> None:
    rd = tmp_path / "rt"
    rd.mkdir()
    (rd / "soak_report.json").write_text('{"profile": "low"}', encoding="utf-8")
    (rd / "queue_pressure.json").write_text("{}", encoding="utf-8")
    s = minimal_test_settings(runtime_state_dir=str(rd))
    out = tmp_path / "bundle.zip"
    manifest = write_runtime_bundle(rd, out, s, include_html=False, fail_on_missing=False)
    assert out.is_file()
    names = _zip_names(out)
    assert f"{BUNDLE_DIR_NAME}/benchmark.json" in names
    assert f"{BUNDLE_DIR_NAME}/manifest.json" in names
    assert f"{BUNDLE_DIR_NAME}/soak_report.json" in names
    assert "soak_report.html" not in manifest["missing_files"]


def test_graceful_missing_optional(tmp_path: Path) -> None:
    rd = tmp_path / "empty_rt"
    rd.mkdir()
    s = minimal_test_settings(runtime_state_dir=str(rd))
    out = tmp_path / "b2.zip"
    manifest = write_runtime_bundle(rd, out, s, include_html=False, fail_on_missing=False)
    assert "soak_report.json" in manifest["missing_files"]
    assert "queue_pressure.json" in manifest["missing_files"]


def test_fail_on_missing_raises(tmp_path: Path) -> None:
    rd = tmp_path / "e"
    rd.mkdir()
    s = minimal_test_settings(runtime_state_dir=str(rd))
    with pytest.raises(RuntimeError, match="missing optional"):
        write_runtime_bundle(rd, tmp_path / "x.zip", s, fail_on_missing=True)


def test_manifest_keys_and_structure(tmp_path: Path) -> None:
    rd = tmp_path / "r"
    rd.mkdir()
    s = minimal_test_settings(runtime_state_dir=str(rd))
    manifest = write_runtime_bundle(rd, tmp_path / "m.zip", s)
    for key in (
        "generated_at",
        "hostname",
        "python_version",
        "platform",
        "git_sha",
        "bundle_version",
        "included_files",
        "missing_files",
        "runtime_dir",
        "artifact_sizes",
        "total_size_bytes",
    ):
        assert key in manifest
    assert isinstance(manifest["included_files"], list)
    assert isinstance(manifest["artifact_sizes"], dict)
    assert manifest["included_files"] == sorted(manifest["included_files"])
    assert list(manifest["artifact_sizes"].keys()) == sorted(manifest["artifact_sizes"])


def test_deterministic_manifest_field_order(tmp_path: Path) -> None:
    rd = tmp_path / "d1"
    rd.mkdir()
    s = minimal_test_settings(runtime_state_dir=str(rd))
    m1 = write_runtime_bundle(rd, tmp_path / "a.zip", s)
    m2 = write_runtime_bundle(rd, tmp_path / "b.zip", s)
    k1 = [k for k in m1 if k != "generated_at"]
    k2 = [k for k in m2 if k != "generated_at"]
    assert k1 == k2


def test_corrupt_timeline_still_bundles(tmp_path: Path) -> None:
    rd = tmp_path / "cor"
    rd.mkdir()
    (rd / "operational_timeline.json").write_text("{broken", encoding="utf-8")
    s = minimal_test_settings(runtime_state_dir=str(rd))
    out = tmp_path / "c.zip"
    manifest = write_runtime_bundle(rd, out, s)
    with zipfile.ZipFile(out) as zf:
        integrity = json.loads(zf.read(f"{BUNDLE_DIR_NAME}/integrity.json").decode())
    assert any("invalid_json" in x for x in integrity.get("timeline_issues", []))


def test_include_html_excludes_html_when_false(tmp_path: Path) -> None:
    rd = tmp_path / "h"
    rd.mkdir()
    (rd / "soak_report.json").write_text("{}", encoding="utf-8")
    s = minimal_test_settings(runtime_state_dir=str(rd))
    out = tmp_path / "h.zip"
    write_runtime_bundle(rd, out, s, include_html=False)
    names = _zip_names(out)
    assert f"{BUNDLE_DIR_NAME}/soak_report.html" not in names


def test_include_html_expects_html(tmp_path: Path) -> None:
    rd = tmp_path / "h2"
    rd.mkdir()
    (rd / "soak_report.json").write_text("{}", encoding="utf-8")
    s = minimal_test_settings(runtime_state_dir=str(rd))
    m = write_runtime_bundle(rd, tmp_path / "h2.zip", s, include_html=True)
    assert "soak_report.html" in m["missing_files"]


def test_metadata_environment_and_manifest_extra(tmp_path: Path) -> None:
    rd = tmp_path / "meta"
    rd.mkdir()
    meta_path = tmp_path / "meta.json"
    meta_path.write_text(
        json.dumps(
            {"soak_profile": "burst", "sample_transport_enabled": True, "manifest_extra": {"ci_job": "nightly"}},
        ),
        encoding="utf-8",
    )
    s = minimal_test_settings(runtime_state_dir=str(rd))
    out = tmp_path / "meta.zip"
    manifest = write_runtime_bundle(
        rd,
        out,
        s,
        metadata=json.loads(meta_path.read_text(encoding="utf-8")),
    )
    assert manifest.get("ci_job") == "nightly"
    with zipfile.ZipFile(out) as zf:
        env = json.loads(zf.read(f"{BUNDLE_DIR_NAME}/environment.json").decode())
    assert env["soak_profile"] == "burst"
    assert env["sample_transport_enabled"] is True


def test_collect_runtime_artifacts_missing_list(tmp_path: Path) -> None:
    rd = tmp_path / "col"
    rd.mkdir()
    s = minimal_test_settings(runtime_state_dir=str(rd))
    c = collect_runtime_artifacts(rd, s, include_html=False)
    assert "soak_report.json" in c.missing_files
    assert "queue_pressure.json" in c.missing_files
