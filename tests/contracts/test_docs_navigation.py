"""Documentation navigation and DX layout contracts."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

REQUIRED_DOCS = (
    "docs/START_HERE.md",
    "docs/ARCHITECTURE_MAP.md",
    "docs/ENGINEERING_PHILOSOPHY.md",
    "docs/FAQ.md",
    "docs/CONTRIBUTING.md",
    "docs/REPRODUCIBILITY.md",
    "docs/REPOSITORY_STANDARDS.md",
    "docs/REPOSITORY_MAP.md",
)

DEMO_SCRIPTS = (
    "examples/demo_walkthrough/01_nightly_run.sh",
    "examples/demo_walkthrough/02_runtime_inspection.sh",
    "examples/demo_walkthrough/03_failure_investigation.sh",
    "examples/demo_walkthrough/04_release_validation.sh",
)

DEMO_OUTPUTS = (
    "examples/demo_outputs/runtime-index.txt",
    "examples/demo_outputs/verify-runtime.txt",
    "examples/demo_outputs/audit-runtime.txt",
    "examples/demo_outputs/compare-baseline.txt",
)

MARKDOWN_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _resolve_doc_link(source: Path, target: str) -> Path | None:
    if target.startswith(("http://", "https://", "mailto:")):
        return None
    if target.startswith("#"):
        return None
    clean = target.split("#", 1)[0].strip()
    if not clean:
        return None
    return (source.parent / clean).resolve()


def _internal_links_in(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [m.group(1).strip() for m in MARKDOWN_LINK_RE.finditer(text)]


@pytest.mark.parametrize("rel", REQUIRED_DOCS)
def test_required_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


@pytest.mark.parametrize("rel", DEMO_SCRIPTS)
def test_demo_scripts_exist_and_executable(rel: str) -> None:
    path = REPO / rel
    assert path.is_file(), rel
    assert path.stat().st_mode & 0o111, f"not executable: {rel}"


@pytest.mark.parametrize("rel", DEMO_OUTPUTS)
def test_demo_outputs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_start_here_links_resolve() -> None:
    source = REPO / "docs/START_HERE.md"
    for target in _internal_links_in(source):
        resolved = _resolve_doc_link(source, target)
        if resolved is None:
            continue
        try:
            resolved.relative_to(REPO.resolve())
        except ValueError:
            continue
        assert resolved.exists(), f"START_HERE broken link: {target}"


def test_readme_links_resolve() -> None:
    source = REPO / "README.md"
    broken: list[str] = []
    for target in _internal_links_in(source):
        resolved = _resolve_doc_link(source, target)
        if resolved is None:
            continue
        try:
            resolved.relative_to(REPO.resolve())
        except ValueError:
            continue
        if not resolved.exists():
            broken.append(f"{target} -> {resolved}")
    assert not broken, "README broken links:\n" + "\n".join(broken)


def test_engineering_philosophy_complexity_rule() -> None:
    text = (REPO / "docs/ENGINEERING_PHILOSOPHY.md").read_text(encoding="utf-8")
    assert "Complexity growth requires exceptional justification" in text


def test_contributing_complexity_rule() -> None:
    text = (REPO / "docs/CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "Complexity growth requires exceptional justification" in text


def test_architecture_map_ascii_sections() -> None:
    text = (REPO / "docs/ARCHITECTURE_MAP.md").read_text(encoding="utf-8")
    for section in (
        "Runtime flow",
        "Inspection flow",
        "Validation flow",
        "Release flow",
        "Deployment flow",
    ):
        assert section in text


def test_faq_has_kubernetes_question() -> None:
    text = (REPO / "docs/FAQ.md").read_text(encoding="utf-8")
    assert "Why no Kubernetes?" in text
    assert "Why frozen contracts?" in text


def test_make_demo_runtime() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "demo-runtime"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "runtime-nightly" in proc.stdout
    assert "demo_walkthrough" in proc.stdout


def test_make_docs_map() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "docs-map"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "START_HERE" in proc.stdout
    assert "ARCHITECTURE_MAP" in proc.stdout
    assert "REPRODUCIBILITY" in proc.stdout
