"""Immutable baseline integration tests. Fixture-only, offline."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from utils.immutable_archive import build_immutable_archive_bundle
from utils.ops_schema_governance import sha256_file
from utils.repository_fingerprint import build_repository_fingerprint

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "tools" / "fixtures" / "ops_history"
FROZEN = "2026-05-16T12:00:00Z"


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPS_FROZEN_UTC", FROZEN)


def _stable_fingerprint(fp: dict) -> dict:
    out = dict(fp)
    out.pop("generated_at", None)
    out.pop("content_sha256", None)
    git = dict(out.get("git") or {})
    git.pop("head", None)
    out["git"] = git
    return out


def test_repository_fingerprint_stable() -> None:
    a = _stable_fingerprint(build_repository_fingerprint(REPO))
    b = _stable_fingerprint(build_repository_fingerprint(REPO))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_immutable_archive_reproducible(tmp_path: Path) -> None:
    kwargs = dict(
        repo_root=REPO,
        history_dir=FIXTURES,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        archive_root=tmp_path / "immutable",
    )
    r1 = build_immutable_archive_bundle(**kwargs)
    r2 = build_immutable_archive_bundle(**kwargs)
    m1 = json.loads((Path(r1["archive_dir"]) / "manifest.json").read_text(encoding="utf-8"))
    m2 = json.loads((Path(r2["archive_dir"]) / "manifest.json").read_text(encoding="utf-8"))
    assert m1["files"] == m2["files"]


def test_archive_checksums_match(tmp_path: Path) -> None:
    result = build_immutable_archive_bundle(
        repo_root=REPO,
        history_dir=FIXTURES,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        archive_root=tmp_path / "immutable",
    )
    root = Path(result["archive_dir"])
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        assert sha256_file(root / entry["path"]) == entry["sha256"]


def test_certification_artifacts_exist() -> None:
    assert (REPO / "docs/releases/immutable_repository_certification.md").is_file()
    assert (REPO / "docs/releases/stewardship_preservation_declaration.md").is_file()
    assert (REPO / "docs/architecture/ADR-036-immutable-stewardship-certification.md").is_file()


def test_freeze_integrity_compatible(tmp_path: Path) -> None:
    result = build_immutable_archive_bundle(
        repo_root=REPO,
        history_dir=FIXTURES,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        archive_root=tmp_path / "immutable",
    )
    assert result["freeze_status"] in ("OK", "WARNING")


def test_frozen_env() -> None:
    assert os.environ.get("OPS_FROZEN_UTC") == FROZEN
