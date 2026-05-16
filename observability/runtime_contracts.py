"""Frozen runtime operational contracts (stabilization SSOT; not a governance subsystem)."""

from __future__ import annotations

from observability.runtime_capabilities import CANONICAL_DEPLOYMENT_PROFILE, CANONICAL_RUNTIME_MODEL
from observability.runtime_index import (
    ARTIFACT_CATEGORIES,
    ARTIFACT_SPECS,
    EXPECTED_GENERATION_ORDERS,
)
from observability.runtime_schema import CURRENT_RUNTIME_SCHEMA_VERSION, SUPPORTED_SCHEMA_VERSIONS

# --- Schema (frozen) ---
FROZEN_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION
FROZEN_SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = tuple(SUPPORTED_SCHEMA_VERSIONS)

# --- Layout ---
RUNTIME_SUBDIR = "runtime"
DEFAULT_OUTPUT_DIR_NAME = "runtime_ops_output"

# --- Artifacts (frozen names, paths, lifecycle) ---
FROZEN_ARTIFACT_FILENAMES: tuple[str, ...] = tuple(s.name for s in ARTIFACT_SPECS)
FROZEN_ARTIFACT_PATHS: tuple[str, ...] = tuple(s.path for s in ARTIFACT_SPECS)
FROZEN_LIFECYCLE_ORDER: tuple[int, ...] = EXPECTED_GENERATION_ORDERS
FROZEN_ARTIFACT_CATEGORIES: frozenset[str] = ARTIFACT_CATEGORIES

REQUIRED_ARTIFACT_FILENAMES: frozenset[str] = frozenset(
    s.name for s in ARTIFACT_SPECS if s.required
)
OPTIONAL_ARTIFACT_FILENAMES: frozenset[str] = frozenset(
    s.name for s in ARTIFACT_SPECS if not s.required
)

# --- Status enums (frozen) ---
STANDARD_TRI_STATE: frozenset[str] = frozenset({"OK", "WARNING", "FAIL"})
INCIDENT_LEVELS: frozenset[str] = frozenset({"NONE", "WARNING", "ERROR"})

# --- CLI (frozen command names) ---
INSPECTION_CLI_COMMANDS: tuple[str, ...] = (
    "health",
    "verify-runtime",
    "validate-recovery",
    "replay-runtime",
    "check-compatibility",
    "audit-runtime",
    "create-baseline",
    "compare-baseline",
    "inspect-capabilities",
    "inspect-policy",
    "runtime-index",
)

CLI_COMMANDS_WITH_JSON: frozenset[str] = frozenset(INSPECTION_CLI_COMMANDS)
CLI_COMMANDS_WITH_STRICT: frozenset[str] = frozenset(
    {
        "health",
        "verify-runtime",
        "validate-recovery",
        "replay-runtime",
        "check-compatibility",
        "audit-runtime",
        "compare-baseline",
        "inspect-capabilities",
        "inspect-policy",
        "runtime-index",
    },
)
CLI_COMMANDS_WITH_WRITE: frozenset[str] = frozenset(
    {
        "validate-recovery",
        "check-compatibility",
        "inspect-capabilities",
        "inspect-policy",
        "runtime-index",
    },
)

# --- Runtime model (frozen) ---
FROZEN_RUNTIME_MODEL = CANONICAL_RUNTIME_MODEL
FROZEN_DEPLOYMENT_PROFILE = CANONICAL_DEPLOYMENT_PROFILE

# --- Experimental (documented; not contract-guaranteed) ---
EXPERIMENTAL_SEMANTICS: tuple[str, ...] = (
    "optional_baseline_drift",
    "optional_capability_execution_mode_hint",
    "future_compatible_schema_versions",
)
