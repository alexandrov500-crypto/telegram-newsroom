"""Smoke tests for deterministic runtime manifest (no network)."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from observability.runtime_manifest import (
    MANIFEST_KEY_ORDER,
    build_runtime_manifest,
    calculate_file_checksum,
    default_runtime_manifest_path,
    load_runtime_manifest,
    rebuild_runtime_manifest,
    write_runtime_manifest,
)


def _write(p: Path, text: str = "{}") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_manifest_schema_and_key_order(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    _write(rt / "health_snapshot.json", '{"pipeline_status":"OK"}')
    _write(rt / "runtime_report.json", '{"incident_level":"NONE"}')
    _write(od / "qualification.json", '{"qualification_status":"OK"}')
    (od / "runtime_bundle.zip").write_bytes(b"zip-bytes")

    manifest = build_runtime_manifest(output_dir=od)
    assert list(manifest.keys()) == list(MANIFEST_KEY_ORDER)
    assert manifest["schema_version"] == 1
    assert manifest["artifact_count"] == len(manifest["artifacts"])
    names = [a["name"] for a in manifest["artifacts"]]
    assert names == sorted(names)
    assert "health_snapshot.json" in names
    assert "runtime_report.json" in names
    assert manifest["bundle"]["exists"] is True
    assert manifest["bundle"]["sha256"] == calculate_file_checksum(od / "runtime_bundle.zip")


def test_deterministic_json_write(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    body = '{"x":1}'
    _write(rt / "health_snapshot.json", body)
    _write(rt / "runtime_report.json", body)

    m1 = build_runtime_manifest(output_dir=od)
    m2 = build_runtime_manifest(output_dir=od)
    m1["generated_at"] = "2026-01-01T00:00:00Z"
    m2["generated_at"] = "2026-01-01T00:00:00Z"
    p = default_runtime_manifest_path(od)
    write_runtime_manifest(p, m1)
    write_runtime_manifest(p, m2)
    assert p.read_text(encoding="utf-8") == json.dumps(
        {k: m1[k] for k in MANIFEST_KEY_ORDER},
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"


def test_checksum_and_load(tmp_path: Path) -> None:
    f = tmp_path / "blob.bin"
    data = b"deterministic-payload"
    f.write_bytes(data)
    expected = hashlib.sha256(data).hexdigest()
    assert calculate_file_checksum(f) == expected
    assert calculate_file_checksum(tmp_path / "missing") is None

    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    _write(rt / "health_snapshot.json")
    _write(rt / "runtime_report.json")
    path = rebuild_runtime_manifest(od)
    loaded = load_runtime_manifest(path)
    assert loaded is not None
    assert loaded["schema_version"] == 1


def test_manifest_idempotency_same_artifacts(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    _write(rt / "health_snapshot.json", '{"a":1}')
    _write(rt / "runtime_report.json", '{"b":2}')

    m1 = build_runtime_manifest(output_dir=od)
    m2 = build_runtime_manifest(output_dir=od)
    for m in (m1, m2):
        m.pop("generated_at", None)
    assert m1 == m2


def test_optional_artifacts_omitted_when_missing(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    _write(rt / "health_snapshot.json")
    _write(rt / "runtime_report.json")

    manifest = build_runtime_manifest(output_dir=od)
    names = {a["name"] for a in manifest["artifacts"]}
    assert "qualification.json" not in names
    assert "ops_benchmark.json" not in names
    assert manifest["bundle"]["exists"] is False
