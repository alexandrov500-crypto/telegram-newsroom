"""Unified deterministic runtime artifact index (stdlib, inspection catalog only)."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from observability.runtime_capabilities import CANONICAL_RUNTIME_MODEL
from observability.runtime_schema import CURRENT_RUNTIME_SCHEMA_VERSION

IndexStatus = Literal["OK", "WARNING", "FAIL"]

RUNTIME_INDEX_REL = Path("runtime") / "runtime_index.json"

INDEX_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION

ARTIFACT_CATEGORIES: frozenset[str] = frozenset(
    {
        "health",
        "reporting",
        "verification",
        "recovery",
        "compatibility",
        "audit",
        "baseline",
        "capabilities",
        "policy",
    },
)

INDEX_KEY_ORDER: tuple[str, ...] = (
    "artifact_categories",
    "artifact_count",
    "artifacts",
    "generated_at",
    "index_status",
    "runtime_model",
    "schema_version",
)


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    path: str
    category: str
    required: bool
    status_field: str
    generation_order: int


# Deterministic nightly lifecycle order (documented in ADR-014).
ARTIFACT_SPECS: tuple[ArtifactSpec, ...] = (
    ArtifactSpec(
        "health_snapshot.json",
        "runtime/health_snapshot.json",
        "health",
        True,
        "pipeline_status",
        1,
    ),
    ArtifactSpec(
        "runtime_report.json",
        "runtime/runtime_report.json",
        "reporting",
        True,
        "incident_level",
        2,
    ),
    ArtifactSpec(
        "runtime_manifest.json",
        "runtime/runtime_manifest.json",
        "verification",
        True,
        "bundle_status",
        3,
    ),
    ArtifactSpec(
        "recovery_report.json",
        "runtime/recovery_report.json",
        "recovery",
        True,
        "recovery_status",
        4,
    ),
    ArtifactSpec(
        "compatibility_report.json",
        "runtime/compatibility_report.json",
        "compatibility",
        True,
        "compatibility_status",
        5,
    ),
    ArtifactSpec(
        "qualification_history.json",
        "runtime/qualification_history.json",
        "audit",
        True,
        "qualification_status",
        6,
    ),
    ArtifactSpec(
        "audit_snapshot.json",
        "runtime/audit_snapshot.json",
        "audit",
        True,
        "audit_status",
        7,
    ),
    ArtifactSpec(
        "runtime_baseline.json",
        "runtime/runtime_baseline.json",
        "baseline",
        False,
        "baseline_status",
        8,
    ),
    ArtifactSpec(
        "drift_report.json",
        "runtime/drift_report.json",
        "baseline",
        False,
        "drift_status",
        9,
    ),
    ArtifactSpec(
        "runtime_capabilities.json",
        "runtime/runtime_capabilities.json",
        "capabilities",
        True,
        "capability_status",
        10,
    ),
    ArtifactSpec(
        "capability_report.json",
        "runtime/capability_report.json",
        "capabilities",
        True,
        "capability_validation_status",
        11,
    ),
    ArtifactSpec(
        "runtime_policy.json",
        "runtime/runtime_policy.json",
        "policy",
        True,
        "policy_status",
        12,
    ),
    ArtifactSpec(
        "policy_report.json",
        "runtime/policy_report.json",
        "policy",
        True,
        "policy_validation_status",
        13,
    ),
    ArtifactSpec(
        "runtime_index.json",
        "runtime/runtime_index.json",
        "reporting",
        True,
        "index_status",
        14,
    ),
)

EXPECTED_GENERATION_ORDERS: tuple[int, ...] = tuple(s.generation_order for s in ARTIFACT_SPECS)


def default_runtime_index_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / RUNTIME_INDEX_REL


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _schema_version_for_file(path: Path) -> int | None:
    doc = _load_json(path)
    if doc is None:
        return None
    raw = doc.get("schema_version")
    try:
        if isinstance(raw, int) and raw > 0:
            return raw
    except (TypeError, ValueError):
        return None
    return None


def _artifact_entry(spec: ArtifactSpec, base: Path, *, present: bool) -> dict[str, Any]:
    full = base / spec.path
    entry: dict[str, Any] = {
        "name": spec.name,
        "path": spec.path,
        "category": spec.category,
        "schema_version": _schema_version_for_file(full) if present else None,
        "required": spec.required,
        "status_field": spec.status_field,
        "generation_order": spec.generation_order,
    }
    return entry


def build_runtime_index(output_dir: Path) -> dict[str, Any]:
    """Build deterministic catalog of runtime artifacts under ``output_dir``."""
    base = output_dir.expanduser().resolve()
    artifacts: list[dict[str, Any]] = []
    categories: dict[str, int] = {c: 0 for c in sorted(ARTIFACT_CATEGORIES)}

    for spec in ARTIFACT_SPECS:
        present = (base / spec.path).is_file()
        if present:
            categories[spec.category] = categories.get(spec.category, 0) + 1
        artifacts.append(_artifact_entry(spec, base, present=present))

    validation = validate_runtime_index(
        {
            "artifacts": artifacts,
            "artifact_categories": categories,
        },
        base,
    )

    index: dict[str, Any] = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "index_status": validation["index_validation_status"],
        "runtime_model": CANONICAL_RUNTIME_MODEL,
        "artifact_count": len(ARTIFACT_SPECS),
        "artifacts": artifacts,
        "artifact_categories": {k: categories[k] for k in sorted(categories)},
    }
    return {k: index[k] for k in INDEX_KEY_ORDER}


def load_runtime_index(path: Path) -> dict[str, Any] | None:
    data = _load_json(path.expanduser().resolve())
    if data is None:
        return None
    return {k: data[k] for k in INDEX_KEY_ORDER if k in data}


def validate_runtime_index(
    index: dict[str, Any],
    output_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate index consistency (read-only)."""
    failures: list[str] = []
    warnings: list[str] = []

    artifacts = index.get("artifacts") or []
    if not isinstance(artifacts, list):
        failures.append("invalid_artifacts:type")
        artifacts = []

    names: list[str] = []
    orders: list[int] = []
    for ent in artifacts:
        if not isinstance(ent, dict):
            failures.append("invalid_artifact_entry:type")
            continue
        name = str(ent.get("name") or "")
        if name in names:
            failures.append(f"duplicate_artifact_name:{name}")
        names.append(name)
        try:
            orders.append(int(ent.get("generation_order")))
        except (TypeError, ValueError):
            failures.append(f"invalid_generation_order:{name}")

        cat = str(ent.get("category") or "")
        if cat not in ARTIFACT_CATEGORIES:
            failures.append(f"unknown_category:{cat}")

        for meta in ent:
            if meta not in (
                "name",
                "path",
                "category",
                "schema_version",
                "required",
                "status_field",
                "generation_order",
            ):
                warnings.append(f"unknown_optional_metadata:{name}:{meta}")

    if orders != sorted(orders):
        failures.append("invalid_generation_order:sequence_not_sorted")

    if orders and orders != list(EXPECTED_GENERATION_ORDERS[: len(orders)]):
        failures.append("invalid_generation_order:lifecycle_mismatch")

    spec_by_name = {s.name: s for s in ARTIFACT_SPECS}
    if output_dir is not None:
        base = output_dir.expanduser().resolve()
        for spec in ARTIFACT_SPECS:
            present = (base / spec.path).is_file()
            if spec.name == "runtime_index.json" and not present:
                # Index is written last; absence during pre-write validation is expected.
                warnings.append("index_not_yet_materialized")
                continue
            if spec.required and not present:
                failures.append(f"missing_required_artifact:{spec.name}")
            elif not spec.required and not present:
                warnings.append(f"missing_optional_artifact:{spec.name}")
    else:
        for ent in artifacts:
            if not isinstance(ent, dict):
                continue
            name = str(ent.get("name") or "")
            spec = spec_by_name.get(name)
            if spec and spec.required and ent.get("schema_version") is None:
                failures.append(f"missing_required_artifact:{name}")

    failures = sorted(set(failures))
    warnings = sorted(set(warnings))

    if failures:
        status: IndexStatus = "FAIL"
    elif warnings:
        status = "WARNING"
    else:
        status = "OK"

    return {
        "index_validation_status": status,
        "index_failures": failures,
        "index_warnings": warnings,
    }


def write_runtime_index(path: Path, index: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: index[k] for k in INDEX_KEY_ORDER if k in index}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def update_runtime_index(output_dir: Path) -> Path:
    """Build, validate, and atomically write the latest runtime index."""
    base = output_dir.expanduser().resolve()
    index = build_runtime_index(base)
    validation = validate_runtime_index(index, base)
    index = dict(index)
    index["index_status"] = validation["index_validation_status"]
    ordered = {k: index[k] for k in INDEX_KEY_ORDER}
    return write_runtime_index(default_runtime_index_path(base), ordered)


def strict_index_exit_code(index: dict[str, Any], *, strict: bool) -> int:
    st = str(index.get("index_status") or "FAIL")
    if st == "FAIL":
        return 1
    if strict and st != "OK":
        return 1
    return 0


def render_index_summary(index: dict[str, Any]) -> str:
    lines = [
        "Runtime index summary",
        "",
        "Runtime index is a deterministic inspection catalog, not a workflow engine.",
        "",
        f"Index status: {index.get('index_status', 'UNKNOWN')}",
        f"Runtime model: {index.get('runtime_model')}",
        f"Artifact count: {index.get('artifact_count')}",
    ]
    cats = index.get("artifact_categories") or {}
    if cats:
        lines.append("")
        lines.append("Artifact categories:")
        for cat in sorted(cats):
            lines.append(f"  {cat}: {cats[cat]}")
    lines.append("")
    lines.append("Generation order:")
    for ent in index.get("artifacts") or []:
        if isinstance(ent, dict):
            present = "present" if ent.get("schema_version") is not None else "missing"
            lines.append(
                f"  {ent.get('generation_order')}. {ent.get('name')} "
                f"[{ent.get('category')}] ({present})",
            )
    status = str(index.get("index_status") or "FAIL")
    if status in ("FAIL", "WARNING"):
        lines.extend(
            [
                "",
                "Operator actions:",
                "  - Ensure OUTPUT_DIR points at a completed nightly (default: ./runtime_ops_output)",
                "  - Run: make runtime-nightly RUNTIME_DIR=./var/runtime OUTPUT_DIR=$OUTPUT_DIR",
                "  - Re-run: make runtime-index OUTPUT_DIR=$OUTPUT_DIR",
                "  - Docs: docs/OPERATOR_QUICKSTART.md",
            ],
        )
    return "\n".join(lines) + "\n"


def lifecycle_ordering_documentation() -> list[tuple[int, str, str]]:
    """Return (order, name, category) for docs and tests."""
    return [(s.generation_order, s.name, s.category) for s in ARTIFACT_SPECS]
