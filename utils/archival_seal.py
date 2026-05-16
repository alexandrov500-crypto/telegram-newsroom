"""Archival integrity seal (v3.2 terminal closure). Read-only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from utils.freeze_integrity import FREEZE_TAG, write_json_deterministic
from utils.immutable_archive import default_immutable_archive_root
from utils.ops_tooling import frozen_utc_now
from utils.repository_fingerprint import (
    VALIDATION_TARGETS,
    build_repository_fingerprint,
    default_integrity_root,
)

SEAL_SCHEMA_VERSION = 1
MAX_SEAL_BYTES = 256 * 1024

CANONICAL_ENTRY_POINTS = (
    "docs/START_HERE.md",
    "docs/MAINTAINERS_GUIDE.md",
    "docs/releases/v3_2_publication_manifest.md",
    "docs/releases/repository_terminal_state.md",
    "docs/releases/immutable_repository_certification.md",
)

GOVERNANCE_REFERENCES = (
    "docs/architecture/ADR-036-immutable-stewardship-certification.md",
    "docs/governance/governance_preservation_audit.md",
    "docs/governance/final_repository_preservation_audit.md",
    "docs/releases/stewardship_preservation_declaration.md",
    "docs/releases/v3_2_archival_closure_report.md",
)


def _ref(path: Path, repo_root: Path) -> dict[str, str]:
    if not path.is_file():
        rel = str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path)
        return {"path": rel.replace("\\", "/"), "present": "false"}
    rel = str(path.relative_to(repo_root)).replace("\\", "/")
    data = path.read_bytes()
    return {
        "path": rel,
        "present": "true",
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": str(len(data)),
    }


def build_archival_integrity_seal(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[1]
    integrity_root = default_integrity_root(root)
    archive_root = default_immutable_archive_root(root)

    fp_path = integrity_root / "repository_fingerprint.json"
    fp_data: dict[str, Any] = {}
    if fp_path.is_file():
        fp_data = json.loads(fp_path.read_text(encoding="utf-8"))
    else:
        fp_data = build_repository_fingerprint(root)

    archive_dirs = sorted([d for d in archive_root.iterdir() if d.is_dir() and d.name.isdigit()]) if archive_root.is_dir() else []
    latest_archive = archive_dirs[-1] if archive_dirs else None
    archive_manifest_ref: dict[str, str] = {"present": "false"}
    if latest_archive and (latest_archive / "manifest.json").is_file():
        archive_manifest_ref = _ref(latest_archive / "manifest.json", root)

    seal: dict[str, Any] = {
        "schema_version": SEAL_SCHEMA_VERSION,
        "read_only": True,
        "offline": True,
        "generated_at": frozen_utc_now(),
        "freeze_tag": FREEZE_TAG,
        "recommended_archival_tag": "v3.2-archival-baseline",
        "repository_fingerprint": {
            "path": str(fp_path.relative_to(root)).replace("\\", "/") if fp_path.is_file() else "var/stewardship_integrity/repository_fingerprint.json",
            "content_sha256": fp_data.get("content_sha256", ""),
        },
        "immutable_archive": archive_manifest_ref,
        "canonical_entry_points": [_ref(root / p, root) for p in CANONICAL_ENTRY_POINTS],
        "governance_references": [_ref(root / p, root) for p in GOVERNANCE_REFERENCES],
        "validation_targets": sorted([*VALIDATION_TARGETS, "archival-freeze-validate"]),
        "stewardship_references": [
            _ref(root / "docs/releases/stewardship_state_declaration.md", root),
            _ref(root / "docs/releases/v3_2_stewardship_handoff.md", root),
        ],
    }
    raw = json.dumps(seal, indent=2, sort_keys=True)
    if len(raw.encode("utf-8")) > MAX_SEAL_BYTES:
        raise ValueError("integrity seal exceeds max size")
    seal["seal_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return seal


def seal_markdown(seal: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Archival integrity seal",
            "",
            f"Generated: {seal.get('generated_at')}",
            f"Freeze tag: `{seal.get('freeze_tag')}`",
            f"Recommended archival tag: `{seal.get('recommended_archival_tag')}`",
            f"Seal SHA-256: `{seal.get('seal_sha256', '')}`",
            "",
            f"Repository fingerprint: `{((seal.get('repository_fingerprint') or {}).get('content_sha256'))}`",
            "",
            "## Validation targets",
            "",
            *[f"- `{t}`" for t in seal.get("validation_targets") or []],
            "",
        ]
    )


def write_archival_seal(repo_root: Path) -> dict[str, str]:
    archive_root = default_immutable_archive_root(repo_root)
    archive_root.mkdir(parents=True, exist_ok=True)
    seal = build_archival_integrity_seal(repo_root)
    json_path = archive_root / "integrity_seal.json"
    md_path = archive_root / "integrity_seal.md"
    write_json_deterministic(json_path, seal)
    md_path.write_text(seal_markdown(seal), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
