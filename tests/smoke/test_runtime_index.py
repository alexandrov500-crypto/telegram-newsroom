"""Smoke tests for unified runtime artifact index."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from observability.runtime_index import (
    ARTIFACT_SPECS,
    EXPECTED_GENERATION_ORDERS,
    INDEX_KEY_ORDER,
    build_runtime_index,
    default_runtime_index_path,
    lifecycle_ordering_documentation,
    load_runtime_index,
    strict_index_exit_code,
    update_runtime_index,
    validate_runtime_index,
    write_runtime_index,
)

REPO = Path(__file__).resolve().parents[2]


def _seed_all(od: Path) -> None:
    rt = od / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    for spec in ARTIFACT_SPECS:
        if spec.name == "runtime_index.json":
            continue
        p = od / spec.path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"schema_version": 1, spec.status_field: "OK"}), encoding="utf-8")


def test_deterministic_ordering_and_unique_names(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_all(od)
    index = build_runtime_index(od)
    names = [a["name"] for a in index["artifacts"]]
    orders = [a["generation_order"] for a in index["artifacts"]]
    assert len(names) == len(set(names))
    assert orders == list(EXPECTED_GENERATION_ORDERS)
    assert list(index.keys()) == list(INDEX_KEY_ORDER)


def test_generation_order_validation_fail(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_all(od)
    index = build_runtime_index(od)
    index = dict(index)
    arts = list(index["artifacts"])
    arts[0] = dict(arts[0])
    arts[0]["generation_order"] = 99
    index["artifacts"] = arts
    validation = validate_runtime_index(index, od)
    assert validation["index_validation_status"] == "FAIL"
    assert any("generation_order" in f for f in validation["index_failures"])


def test_category_validation_fail(tmp_path: Path) -> None:
    index = {
        "artifacts": [
            {
                "name": "x.json",
                "path": "runtime/x.json",
                "category": "unknown_cat",
                "schema_version": 1,
                "required": True,
                "status_field": "status",
                "generation_order": 1,
            },
        ],
        "artifact_categories": {},
    }
    validation = validate_runtime_index(index)
    assert validation["index_validation_status"] == "FAIL"
    assert any("unknown_category" in f for f in validation["index_failures"])


def test_missing_required_fail(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    index = build_runtime_index(od)
    assert index["index_status"] == "FAIL"


def test_optional_missing_warning(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_all(od)
    (od / "runtime" / "runtime_baseline.json").unlink(missing_ok=True)
    (od / "runtime" / "drift_report.json").unlink(missing_ok=True)
    index = build_runtime_index(od)
    assert index["index_status"] == "WARNING"


def test_index_idempotency(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_all(od)
    a = build_runtime_index(od)
    b = build_runtime_index(od)
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


def test_deterministic_json_write(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_all(od)
    index = build_runtime_index(od)
    p = default_runtime_index_path(od)
    write_runtime_index(p, index)
    loaded = load_runtime_index(p)
    assert loaded is not None
    assert loaded["artifact_count"] == len(ARTIFACT_SPECS)


def test_lifecycle_documentation_order() -> None:
    doc = lifecycle_ordering_documentation()
    assert doc[0][0] == 1
    assert doc[-1][1] == "runtime_index.json"


def test_strict_exit_codes() -> None:
    assert strict_index_exit_code({"index_status": "OK"}, strict=True) == 0
    assert strict_index_exit_code({"index_status": "WARNING"}, strict=True) == 1
    assert strict_index_exit_code({"index_status": "FAIL"}, strict=False) == 1


def test_update_runtime_index(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_all(od)
    path = update_runtime_index(od)
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["index_status"] in ("OK", "WARNING")


def test_cli_runtime_index_strict(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "runtime-index", "--path", str(od), "--strict"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
