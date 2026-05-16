"""Deterministic runtime manifest with SHA256 checksums (stdlib, latest-only)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from observability.health_snapshot import load_health_snapshot_sidecar_json

from observability.runtime_schema import CURRENT_RUNTIME_SCHEMA_VERSION

MANIFEST_SCHEMA_VERSION = CURRENT_RUNTIME_SCHEMA_VERSION
RUNTIME_MANIFEST_REL = Path("runtime") / "runtime_manifest.json"

ArtifactKind = Literal["required", "optional"]

REQUIRED_SPECS: tuple[tuple[str, str], ...] = (
    ("health_snapshot.json", "runtime/health_snapshot.json"),
    ("runtime_report.json", "runtime/runtime_report.json"),
)

OPTIONAL_SPECS: tuple[tuple[str, str], ...] = (
    ("qualification.json", "qualification.json"),
    ("runtime_bundle.zip", "runtime_bundle.zip"),
    ("ops_benchmark.json", "ops_benchmark.json"),
)

MANIFEST_KEY_ORDER: tuple[str, ...] = (
    "artifact_count",
    "artifacts",
    "bundle",
    "bundle_status",
    "generated_at",
    "qualification_status",
    "schema_version",
)


@dataclass(frozen=True)
class ArtifactSpec:
    name: str
    rel_path: str
    required: bool


def default_runtime_manifest_path(base_dir: Path) -> Path:
    return base_dir.expanduser().resolve() / RUNTIME_MANIFEST_REL


def calculate_file_checksum(path: Path) -> str | None:
    """Return lowercase hex SHA256 of file contents, or None if unreadable."""
    p = path.expanduser().resolve()
    if not p.is_file():
        return None
    h = hashlib.sha256()
    try:
        with p.open("rb") as fh:
            while True:
                chunk = fh.read(65536)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _artifact_entry(
    base: Path, name: str, rel_path: str, *, required: bool
) -> dict[str, Any] | None:
    full = base / rel_path
    if not full.is_file():
        return None
    try:
        size = int(full.stat().st_size)
    except OSError:
        return None
    digest = calculate_file_checksum(full)
    if digest is None:
        return None
    return {
        "name": name,
        "path": rel_path.replace("\\", "/"),
        "required": required,
        "sha256": digest,
        "size_bytes": size,
    }


def _step_status(ops_report: dict[str, Any] | None, step: str) -> str | None:
    if not ops_report:
        return None
    for block in ops_report.get("steps") or []:
        if isinstance(block, dict) and block.get("name") == step:
            return str(block.get("status") or "OK").upper()
    return None


def build_runtime_manifest(
    *,
    output_dir: Path,
    ops_report: dict[str, Any] | None = None,
    qualification: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build manifest describing tracked artifacts under ``output_dir``."""
    base = output_dir.expanduser().resolve()
    qual_doc = qualification
    if qual_doc is None:
        qual_doc = load_health_snapshot_sidecar_json(base / "qualification.json")
    qual_st = "OK"
    if qual_doc:
        qual_st = str(qual_doc.get("qualification_status") or "OK")
    elif ops_report:
        step = _step_status(ops_report, "qualification")
        if step and step != "SKIPPED":
            qual_st = step

    bundle_status = "OK"
    if ops_report:
        step = _step_status(ops_report, "bundle")
        if step and step != "SKIPPED":
            bundle_status = step
    if not (base / "runtime_bundle.zip").is_file():
        bundle_status = "WARNING"

    artifacts: list[dict[str, Any]] = []
    for name, rel in REQUIRED_SPECS:
        ent = _artifact_entry(base, name, rel, required=True)
        if ent is not None:
            artifacts.append(ent)
    for name, rel in OPTIONAL_SPECS:
        ent = _artifact_entry(base, name, rel, required=False)
        if ent is not None:
            artifacts.append(ent)
    artifacts.sort(key=lambda a: str(a["name"]))

    bundle_path = base / "runtime_bundle.zip"
    bundle_block: dict[str, Any] = {
        "exists": bundle_path.is_file(),
        "path": "runtime_bundle.zip",
        "sha256": None,
        "size_bytes": None,
    }
    if bundle_path.is_file():
        try:
            bundle_block["size_bytes"] = int(bundle_path.stat().st_size)
        except OSError:
            pass
        bundle_block["sha256"] = calculate_file_checksum(bundle_path)

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "generated_at": _utc_now_iso(),
        "bundle_status": bundle_status,
        "qualification_status": qual_st,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "bundle": bundle_block,
    }
    return {k: manifest[k] for k in MANIFEST_KEY_ORDER}


def write_runtime_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    dest = path.expanduser().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = {k: manifest[k] for k in MANIFEST_KEY_ORDER if k in manifest}
    payload = json.dumps(ordered, indent=2, sort_keys=True, default=str) + "\n"
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def load_runtime_manifest(path: Path) -> dict[str, Any] | None:
    dest = path.expanduser().resolve()
    if not dest.is_file():
        return None
    try:
        data = json.loads(dest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def rebuild_runtime_manifest(output_dir: Path, *, ops_report: dict[str, Any] | None = None) -> Path:
    """Build and atomically write the latest runtime manifest for ``output_dir``."""
    manifest = build_runtime_manifest(output_dir=output_dir, ops_report=ops_report)
    return write_runtime_manifest(default_runtime_manifest_path(output_dir), manifest)


def all_tracked_specs() -> list[ArtifactSpec]:
    out: list[ArtifactSpec] = []
    for name, rel in REQUIRED_SPECS:
        out.append(ArtifactSpec(name=name, rel_path=rel, required=True))
    for name, rel in OPTIONAL_SPECS:
        out.append(ArtifactSpec(name=name, rel_path=rel, required=False))
    return out
