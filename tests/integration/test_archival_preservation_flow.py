"""Archival preservation flow tests. Fixture-only, offline."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from utils.archival_seal import build_archival_integrity_seal
from utils.immutable_archive import build_immutable_archive_bundle
from utils.repository_fingerprint import build_repository_fingerprint

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "tools" / "fixtures" / "ops_history"
FROZEN = "2026-05-16T12:00:00Z"


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPS_FROZEN_UTC", FROZEN)


def _stable_seal(seal: dict) -> dict:
    out = dict(seal)
    out.pop("generated_at", None)
    out.pop("seal_sha256", None)
    fp = dict(out.get("repository_fingerprint") or {})
    fp.pop("content_sha256", None)
    out["repository_fingerprint"] = fp
    return out


def test_archival_seal_reproducible() -> None:
    a = _stable_seal(build_archival_integrity_seal(REPO))
    b = _stable_seal(build_archival_integrity_seal(REPO))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_publication_manifest_references() -> None:
    text = (REPO / "docs/releases/v3_2_publication_manifest.md").read_text(encoding="utf-8")
    assert "v3.2-operational-tooling-freeze" in text
    assert "archival-freeze-validate" in text
    assert "ab7c92a" in text


def test_immutable_archive_consistent(tmp_path: Path) -> None:
    kwargs = dict(
        repo_root=REPO,
        history_dir=FIXTURES,
        reports_dir=tmp_path / "reports",
        archive_dir=tmp_path / "arch",
        archive_root=tmp_path / "immutable",
    )
    r1 = build_immutable_archive_bundle(**kwargs)
    r2 = build_immutable_archive_bundle(**kwargs)
    assert json.loads((Path(r1["archive_dir"]) / "manifest.json").read_text())["files"] == json.loads(
        (Path(r2["archive_dir"]) / "manifest.json").read_text()
    )["files"]


def test_fingerprint_has_governance_inventory() -> None:
    fp = build_repository_fingerprint(REPO)
    paths = [g["path"] for g in fp.get("governance_inventory") or []]
    assert "docs/releases/stewardship_preservation_declaration.md" in paths


def test_closure_report_exists() -> None:
    assert (REPO / "docs/releases/v3_2_archival_closure_report.md").is_file()
    assert (REPO / "docs/governance/final_repository_preservation_audit.md").is_file()


def test_frozen_env() -> None:
    assert os.environ.get("OPS_FROZEN_UTC") == FROZEN
