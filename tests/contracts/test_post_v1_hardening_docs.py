"""Post-v1 hardening roadmap documentation contracts (planning-only; no runtime changes)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

HARDENING_DOCS = (
    "docs/post_v1_hardening.md",
    "docs/POST_V1_TODO_BACKLOG.md",
    "docs/architecture/POST_V1_ADR_BACKLOG.md",
    "docs/architecture/ADR-019-post-v1-hardening-roadmap-planning-only.md",
    "docs/rfc/README.md",
)

OPT_IN_PHRASES = (
    "opt-in",
    "planning only",
    "not implemented",
)

FORBIDDEN_MANDATE = (
    "mandatory prometheus",
    "add a new runtime artifact",
    "new inspection cli command",
)


@pytest.mark.parametrize("rel", HARDENING_DOCS)
def test_hardening_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_all_rfc_drafts_exist() -> None:
    rfc_dir = REPO / "docs/rfc"
    names = {
        "RFC-001-structured-metrics.md",
        "RFC-002-health-endpoints.md",
        "RFC-003-queue-abstraction.md",
        "RFC-004-pluggable-storage.md",
        "RFC-005-postgresql-migration.md",
        "RFC-006-distributed-scheduling.md",
        "RFC-007-multi-channel-publishing.md",
        "RFC-008-secrets-management.md",
        "RFC-009-ci-runtime-matrix.md",
        "RFC-010-chaos-fault-injection.md",
    }
    present = {p.name for p in rfc_dir.glob("RFC-*.md")}
    assert names <= present


def test_post_v1_hardening_opt_in_and_freeze() -> None:
    text = (REPO / "docs/post_v1_hardening.md").read_text(encoding="utf-8").lower()
    assert any(p in text for p in OPT_IN_PHRASES)
    assert "frozen" in text or "freeze" in text
    assert "14" in text and "runtime" in text
    assert not any(p in text for p in FORBIDDEN_MANDATE)


def test_adr_019_planning_scope() -> None:
    text = (
        REPO / "docs/architecture/ADR-019-post-v1-hardening-roadmap-planning-only.md"
    ).read_text(encoding="utf-8")
    assert "planning-only" in text.lower() or "planning only" in text.lower()
    assert "no runtime behavior" in text.lower() or "documentation scope only" in text.lower()


def test_start_here_links_post_v1_hardening() -> None:
    text = (REPO / "docs/START_HERE.md").read_text(encoding="utf-8")
    assert "post_v1_hardening.md" in text


def test_maintenance_mode_distinguishes_hardening_plan() -> None:
    text = (REPO / "docs/MAINTENANCE_MODE.md").read_text(encoding="utf-8")
    assert "post_v1_hardening.md" in text


def test_docs_map_lists_post_v1_hardening() -> None:
    import subprocess

    proc = subprocess.run(
        ["make", "-C", str(REPO), "docs-map"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "post_v1_hardening" in proc.stdout.lower() or "POST_V1" in proc.stdout
