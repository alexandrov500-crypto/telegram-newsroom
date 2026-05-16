"""Frozen runtime contract tests (stabilization; not smoke/integration)."""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path


from observability.runtime_contracts import (
    CLI_COMMANDS_WITH_JSON,
    CLI_COMMANDS_WITH_STRICT,
    CLI_COMMANDS_WITH_WRITE,
    EXPERIMENTAL_SEMANTICS,
    FROZEN_ARTIFACT_CATEGORIES,
    FROZEN_ARTIFACT_FILENAMES,
    FROZEN_ARTIFACT_PATHS,
    FROZEN_DEPLOYMENT_PROFILE,
    FROZEN_LIFECYCLE_ORDER,
    FROZEN_RUNTIME_MODEL,
    FROZEN_SCHEMA_VERSION,
    FROZEN_SUPPORTED_SCHEMA_VERSIONS,
    INCIDENT_LEVELS,
    INSPECTION_CLI_COMMANDS,
    OPTIONAL_ARTIFACT_FILENAMES,
    REQUIRED_ARTIFACT_FILENAMES,
    STANDARD_TRI_STATE,
)
from observability.runtime_index import ARTIFACT_SPECS, EXPECTED_GENERATION_ORDERS

REPO = Path(__file__).resolve().parents[2]

FROZEN_RUNTIME_HELP_SECTIONS: tuple[str, ...] = (
    "Inspect / catalog:",
    "Verify:",
    "Recovery:",
    "Audit:",
    "Baseline:",
    "Governance (frozen contracts):",
    "Pipeline:",
)

FROZEN_DOCS_MAP_ENTRIES: tuple[str, ...] = (
    "START_HERE.md",
    "ARCHITECTURE_MAP.md",
    "ENGINEERING_PHILOSOPHY.md",
    "REPRODUCIBILITY.md",
    "REPOSITORY_STANDARDS.md",
)

REQUIRED_MAKEFILE_TARGETS: frozenset[str] = frozenset(
    {
        "lint",
        "format-check",
        "contracts",
        "smoke",
        "quality",
        "release-check",
        "ci-test",
        "runtime-help",
        "docs-map",
        "demo-runtime",
        "runtime-nightly",
        "runtime-index",
        "verify-runtime",
    },
)


def test_artifact_filenames_frozen() -> None:
    assert FROZEN_ARTIFACT_FILENAMES == (
        "health_snapshot.json",
        "runtime_report.json",
        "runtime_manifest.json",
        "recovery_report.json",
        "compatibility_report.json",
        "qualification_history.json",
        "audit_snapshot.json",
        "runtime_baseline.json",
        "drift_report.json",
        "runtime_capabilities.json",
        "capability_report.json",
        "runtime_policy.json",
        "policy_report.json",
        "runtime_index.json",
    )


def test_lifecycle_order_frozen() -> None:
    assert FROZEN_LIFECYCLE_ORDER == tuple(range(1, 15))
    assert EXPECTED_GENERATION_ORDERS == FROZEN_LIFECYCLE_ORDER
    orders = [s.generation_order for s in ARTIFACT_SPECS]
    assert orders == list(FROZEN_LIFECYCLE_ORDER)


def test_category_taxonomy_frozen() -> None:
    assert FROZEN_ARTIFACT_CATEGORIES == frozenset(
        {
            "audit",
            "baseline",
            "capabilities",
            "compatibility",
            "health",
            "policy",
            "recovery",
            "reporting",
            "verification",
        },
    )
    for spec in ARTIFACT_SPECS:
        assert spec.category in FROZEN_ARTIFACT_CATEGORIES


def test_required_optional_artifact_sets() -> None:
    assert "runtime_baseline.json" in OPTIONAL_ARTIFACT_FILENAMES
    assert "drift_report.json" in OPTIONAL_ARTIFACT_FILENAMES
    assert "health_snapshot.json" in REQUIRED_ARTIFACT_FILENAMES
    assert "runtime_index.json" in REQUIRED_ARTIFACT_FILENAMES
    assert REQUIRED_ARTIFACT_FILENAMES | OPTIONAL_ARTIFACT_FILENAMES == frozenset(
        FROZEN_ARTIFACT_FILENAMES,
    )


def test_status_enums_frozen() -> None:
    assert STANDARD_TRI_STATE == frozenset({"FAIL", "OK", "WARNING"})
    assert INCIDENT_LEVELS == frozenset({"ERROR", "NONE", "WARNING"})


def test_schema_version_frozen() -> None:
    assert FROZEN_SCHEMA_VERSION == 1
    assert FROZEN_SUPPORTED_SCHEMA_VERSIONS == (1,)


def test_runtime_layout_paths_under_runtime_dir() -> None:
    for path in FROZEN_ARTIFACT_PATHS:
        assert path.startswith("runtime/"), path
        assert path.endswith(".json"), path


def test_cli_command_registry_frozen() -> None:
    assert len(INSPECTION_CLI_COMMANDS) == 11
    assert "runtime-index" in INSPECTION_CLI_COMMANDS
    assert "verify-runtime" in INSPECTION_CLI_COMMANDS


def test_cli_flag_consistency_registry() -> None:
    assert CLI_COMMANDS_WITH_JSON == frozenset(INSPECTION_CLI_COMMANDS)
    assert "create-baseline" not in CLI_COMMANDS_WITH_STRICT
    assert "create-baseline" not in CLI_COMMANDS_WITH_WRITE
    assert CLI_COMMANDS_WITH_WRITE <= CLI_COMMANDS_WITH_STRICT | {"create-baseline"}


def test_cli_modules_expose_standard_flags() -> None:
    cli = importlib.import_module("newsroom.cli.__main__")
    for cmd in INSPECTION_CLI_COMMANDS:
        if cmd == "health":
            continue
        handler = getattr(cli, f"_cmd_{cmd.replace('-', '_')}", None)
        if handler is None and cmd == "verify-runtime":
            handler = cli._cmd_verify_runtime
        assert handler is not None, cmd
        parser = argparse.ArgumentParser()
        if cmd in CLI_COMMANDS_WITH_WRITE:
            from newsroom.cli.inspection_common import add_standard_inspection_args

            add_standard_inspection_args(parser, supports_write=True)
        elif cmd in {"create-baseline", "compare-baseline"}:
            parser.add_argument("--path", type=Path)
            parser.add_argument("--json", action="store_true")
            if cmd == "compare-baseline":
                parser.add_argument("--strict", action="store_true")
        else:
            from newsroom.cli.inspection_common import add_standard_inspection_args

            add_standard_inspection_args(parser, supports_write=False)


def test_strict_tri_state_exit_helper() -> None:
    from newsroom.cli.inspection_common import strict_tri_state_exit

    assert strict_tri_state_exit("OK", strict=False) == 0
    assert strict_tri_state_exit("OK", strict=True) == 0
    assert strict_tri_state_exit("WARNING", strict=True) == 1
    assert strict_tri_state_exit("FAIL", strict=False) == 1


def test_experimental_semantics_documented() -> None:
    assert "optional_baseline_drift" in EXPERIMENTAL_SEMANTICS


def test_runtime_model_and_profile_frozen() -> None:
    assert FROZEN_RUNTIME_MODEL == "single-node"
    assert FROZEN_DEPLOYMENT_PROFILE == "production-lite"


def test_stabilization_docs_exist() -> None:
    for rel in (
        "docs/architecture/RUNTIME_CONTRACTS.md",
        "docs/architecture/RUNTIME_MATURITY.md",
        "docs/architecture/ADR-015-runtime-stabilization-and-contract-freeze.md",
        "docs/OPERATOR_QUICKSTART.md",
        "docs/RUNTIME_LAYOUT_REFERENCE.md",
        "docs/RELEASE_CHECKLIST.md",
    ):
        assert (REPO / rel).is_file(), rel


def test_cli_help_lists_inspection_commands() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "--help"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "runtime-index" in proc.stdout or "inspect" in proc.stdout


def test_runtime_help_stable_sections() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "runtime-help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for section in FROZEN_RUNTIME_HELP_SECTIONS:
        assert section in proc.stdout, section


def test_docs_map_stable_entries() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "docs-map"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for entry in FROZEN_DOCS_MAP_ENTRIES:
        assert entry in proc.stdout, entry


def test_makefile_declares_required_targets() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    for target in sorted(REQUIRED_MAKEFILE_TARGETS):
        assert f"{target}:" in makefile or f"{target} " in makefile, target


def test_cli_registry_matches_newsroom_cli_dispatch() -> None:
    """Each frozen command exposes --help via main() dispatch (top-level help is abbreviated)."""
    for cmd in INSPECTION_CLI_COMMANDS:
        proc = subprocess.run(
            [sys.executable, "-m", "newsroom.cli", cmd, "--help"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, (cmd, proc.stderr)


def test_reproducibility_docs_exist() -> None:
    for rel in (
        "docs/REPRODUCIBILITY.md",
        "docs/REPOSITORY_STANDARDS.md",
        "docs/REPOSITORY_MAP.md",
        "docs/architecture/ADR-016-repository-reproducibility-and-maintenance.md",
        "docs/examples/reproducible_runtime_workflow.md",
        "requirements-dev.txt",
    ):
        assert (REPO / rel).is_file(), rel


def test_version_stability_v1() -> None:
    from newsroom._version import RELEASE_STATUS, VERSION

    assert VERSION == "1.0.0"
    assert RELEASE_STATUS == "stable"


def test_release_check_target_in_makefile() -> None:
    makefile = (REPO / "Makefile").read_text(encoding="utf-8")
    assert "release-check:" in makefile
    assert "test_packaging_consistency" in makefile


def test_stability_and_maintenance_docs_exist() -> None:
    for rel in (
        "docs/STABILITY_GUARANTEES.md",
        "docs/MAINTENANCE_POLICY.md",
        "docs/RELEASE_FINALIZATION.md",
        "SECURITY.md",
        "SUPPORT.md",
        "LICENSE",
    ):
        assert (REPO / rel).is_file(), rel


def test_stability_guarantees_freeze_statement() -> None:
    text = (REPO / "docs/STABILITY_GUARANTEES.md").read_text(encoding="utf-8")
    assert "operationally frozen as of v1.0.0" in text


def test_maintenance_policy_complexity_rule() -> None:
    text = (REPO / "docs/MAINTENANCE_POLICY.md").read_text(encoding="utf-8")
    assert "New architectural layers require exceptional justification" in text
