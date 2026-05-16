"""Lightweight checks that architecture docs exist and stay navigable."""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_ARCH_FILES: tuple[str, ...] = (
    "docs/architecture/README.md",
    "docs/architecture/SYSTEM_OVERVIEW.md",
    "docs/architecture/OPERATIONAL_LIFECYCLE.md",
    "docs/architecture/ADR-001-bounded-runtime-state.md",
    "docs/architecture/ADR-002-static-operational-dashboard.md",
    "docs/architecture/ADR-003-no-orchestration-policy.md",
    "docs/architecture/ADR-004-release-qualification-semantics.md",
    "docs/architecture/ADR-005-runtime-retention-strategy.md",
    "docs/architecture/ADR-006-runtime-reporting-semantics.md",
)


def test_architecture_markdown_files_exist() -> None:
    for rel in _ARCH_FILES:
        p = REPO / rel
        assert p.is_file(), f"missing {rel}"


def test_architecture_readme_links_resolve() -> None:
    text = (REPO / "docs/architecture/README.md").read_text(encoding="utf-8")
    for needle in (
        "SYSTEM_OVERVIEW.md",
        "OPERATIONAL_LIFECYCLE.md",
        "ADR-001-bounded-runtime-state.md",
        "ADR-005-runtime-retention-strategy.md",
    ):
        assert needle in text, needle


def test_system_overview_has_core_sections() -> None:
    t = (REPO / "docs/architecture/SYSTEM_OVERVIEW.md").read_text(encoding="utf-8")
    for needle in ("High-level architecture", "Non-goals", "Deterministic tooling", "Telegram sources"):
        assert needle in t


def test_adrs_have_status_and_context() -> None:
    for rel in _ARCH_FILES:
        if "ADR-" not in rel:
            continue
        body = (REPO / rel).read_text(encoding="utf-8")
        assert "Status: Accepted" in body
        assert "## Context" in body
        assert "## Decision" in body
