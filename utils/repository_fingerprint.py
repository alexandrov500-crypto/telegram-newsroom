"""Repository fingerprint for immutable stewardship baseline (read-only)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from utils.freeze_integrity import FREEZE_TAG, write_json_deterministic
from utils.ops_tooling import frozen_utc_now

FINGERPRINT_SCHEMA_VERSION = 1
MAX_FINGERPRINT_BYTES = 512 * 1024

ADR_V32_GLOBS = ("docs/architecture/ADR-03*.md", "docs/architecture/ADR-034*.md", "docs/architecture/ADR-036*.md")

TOOLING_INVENTORY = (
    "tools/ops_metrics_snapshot.py",
    "tools/queue_introspection.py",
    "tools/publish_timeline_report.py",
    "tools/ops_analytics_aggregate.py",
    "tools/ops_visualize.py",
    "tools/ops_archive.py",
    "tools/generate_shift_handoff.py",
    "tools/validate_ops_schema.py",
    "tools/export_ops_bundle.py",
    "tools/generate_ops_html_report.py",
    "tools/build_ops_release_kit.py",
    "tools/generate_ops_index.py",
    "tools/check_freeze_integrity.py",
    "tools/build_stewardship_audit_bundle.py",
    "tools/build_repository_fingerprint.py",
    "tools/build_immutable_archive_bundle.py",
    "tools/build_archival_integrity_seal.py",
)

UTILS_INVENTORY = (
    "utils/ops_tooling.py",
    "utils/ops_analytics.py",
    "utils/ops_schema_governance.py",
    "utils/ops_bundle.py",
    "utils/ops_release_kit.py",
    "utils/ops_index.py",
    "utils/freeze_integrity.py",
    "utils/stewardship_audit.py",
    "utils/repository_fingerprint.py",
    "utils/immutable_archive.py",
    "utils/archival_seal.py",
)

VALIDATION_TARGETS = (
    "ops-tooling-validate",
    "ops-analytics-validate",
    "ops-bundle-validate",
    "ops-release-validate",
    "stewardship-validate",
    "stewardship-audit-validate",
    "immutable-baseline-validate",
    "archival-freeze-validate",
)

GOVERNANCE_INVENTORY = (
    "docs/governance/long_term_stewardship.md",
    "docs/governance/operational_tooling_maintenance_policy.md",
    "docs/governance/stewardship_operations_calendar.md",
    "docs/governance/drift_detection_policy.md",
    "docs/governance/maintenance_branch_policy.md",
    "docs/governance/governance_preservation_audit.md",
    "docs/releases/immutable_repository_certification.md",
    "docs/releases/stewardship_preservation_declaration.md",
    "docs/releases/stewardship_state_declaration.md",
    "docs/architecture/ADR-036-immutable-stewardship-certification.md",
    "docs/releases/v3_2_publication_manifest.md",
    "docs/releases/v3_2_archival_closure_report.md",
    "docs/releases/repository_terminal_state.md",
    "docs/governance/final_repository_preservation_audit.md",
)


def default_integrity_root(repo_root: Path | None = None) -> Path:
    root = repo_root or Path(__file__).resolve().parents[1]
    return root / "var" / "stewardship_integrity"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_fingerprint(repo_root: Path, rel: str) -> dict[str, str]:
    path = repo_root / rel
    if not path.is_file():
        return {"path": rel, "present": "false"}
    return {"path": rel, "present": "true", "sha256": _sha256_file(path), "bytes": str(path.stat().st_size)}


def _collect_adr_fingerprints(repo_root: Path) -> list[dict[str, str]]:
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for pattern in ADR_V32_GLOBS:
        for path in sorted(repo_root.glob(pattern)):
            rel = str(path.relative_to(repo_root)).replace("\\", "/")
            if rel in seen:
                continue
            seen.add(rel)
            rows.append(_file_fingerprint(repo_root, rel))
    return sorted(rows, key=lambda r: r["path"])


def _git_lineage(repo_root: Path) -> dict[str, Any]:
    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-20", "--grep=v3.2"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        tags = subprocess.run(
            ["git", "tag", "-l", "v3.2*"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        freeze = subprocess.run(
            ["git", "rev-parse", f"{FREEZE_TAG}^{{commit}}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "SKIP", "commits": [], "tags": []}
    return {
        "status": "OK",
        "head": (head.stdout or "").strip(),
        "freeze_tag": FREEZE_TAG,
        "freeze_commit": (freeze.stdout or "").strip() if freeze.returncode == 0 else "",
        "tags": sorted((tags.stdout or "").split()),
        "recent_v32_commits": [ln.strip() for ln in (log.stdout or "").splitlines() if ln.strip()],
    }


def build_repository_fingerprint(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or Path(__file__).resolve().parents[1]
    payload: dict[str, Any] = {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "read_only": True,
        "offline": True,
        "generated_at": frozen_utc_now(),
        "freeze_tag": FREEZE_TAG,
        "git": _git_lineage(root),
        "adr_inventory": _collect_adr_fingerprints(root),
        "tooling_inventory": [_file_fingerprint(root, p) for p in TOOLING_INVENTORY],
        "utils_inventory": [_file_fingerprint(root, p) for p in UTILS_INVENTORY],
        "validation_targets": sorted(VALIDATION_TARGETS),
        "governance_inventory": [_file_fingerprint(root, p) for p in GOVERNANCE_INVENTORY],
    }
    raw = json.dumps(payload, indent=2, sort_keys=True)
    if len(raw.encode("utf-8")) > MAX_FINGERPRINT_BYTES:
        raise ValueError("fingerprint exceeds max size")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    payload["content_sha256"] = digest
    return payload


def fingerprint_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Repository fingerprint",
        "",
        f"Generated: {data.get('generated_at')}",
        f"Freeze tag: `{data.get('freeze_tag')}`",
        f"Content SHA-256: `{data.get('content_sha256', '')}`",
        "",
        "## Git lineage",
        "",
        f"- HEAD: `{((data.get('git') or {}).get('head'))}`",
        f"- Freeze commit: `{((data.get('git') or {}).get('freeze_commit'))}`",
        "",
        "## Inventories",
        "",
        f"- ADR entries: {len(data.get('adr_inventory') or [])}",
        f"- Tooling files: {len(data.get('tooling_inventory') or [])}",
        f"- Governance docs: {len(data.get('governance_inventory') or [])}",
        f"- Validation targets: {len(data.get('validation_targets') or [])}",
        "",
    ]
    return "\n".join(lines)


def write_fingerprint_outputs(repo_root: Path, integrity_root: Path | None = None) -> dict[str, str]:
    root = integrity_root or default_integrity_root(repo_root)
    root.mkdir(parents=True, exist_ok=True)
    data = build_repository_fingerprint(repo_root)
    json_path = root / "repository_fingerprint.json"
    md_path = root / "repository_fingerprint.md"
    write_json_deterministic(json_path, data)
    md_path.write_text(fingerprint_markdown(data), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
