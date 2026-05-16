"""Unified runtime artifact zip bundle (CI / postmortem, production-lite)."""

from __future__ import annotations

import asyncio
import json
import os
import platform
import socket
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BUNDLE_VERSION = "1"
BUNDLE_DIR_NAME = "runtime_bundle"
# Fixed ZIP timestamps for lightweight reproducible archives (ZIP epoch).
ZIP_FIXED_DTIME = (1980, 1, 1, 0, 0, 0)


def _zip_write_file(zf: zipfile.ZipFile, source: Path, arcname: str) -> None:
    data = source.read_bytes()
    info = zipfile.ZipInfo(arcname)
    info.date_time = ZIP_FIXED_DTIME
    info.compress_type = zipfile.ZIP_DEFLATED
    zf.writestr(info, data)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_runtime_benchmark_module() -> Any:
    import importlib.util

    path = _repo_root() / "tools" / "runtime_benchmark.py"
    spec = importlib.util.spec_from_file_location("_newsroom_runtime_benchmark", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git_sha_short() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_repo_root()),
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return out.decode("utf-8", errors="replace").strip()[:40] or None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def _json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, indent=2, sort_keys=True, default=str).encode("utf-8")


def _read_optional_file(path: Path) -> bytes | None:
    if not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _build_integrity_payload(runtime_dir: str) -> dict[str, Any]:
    from utils.runtime_integrity import (
        summarize_runtime_state_dir,
        validate_event_history,
        validate_operational_timeline,
        validate_suppression_state,
    )

    return {
        "timeline_issues": validate_operational_timeline(runtime_dir),
        "suppression_issues": validate_suppression_state(runtime_dir),
        "event_history_issues": validate_event_history(runtime_dir),
        "summary": summarize_runtime_state_dir(runtime_dir),
    }


def _build_runtime_summary_payload(runtime_dir: str, settings: Any) -> dict[str, Any]:
    from utils.runtime_integrity import summarize_runtime_state_dir
    from utils.soak_simulation import collect_bounded_state_report

    return {
        "summarize_runtime_state_dir": summarize_runtime_state_dir(runtime_dir),
        "bounded_state_report": collect_bounded_state_report(settings),
    }


def _build_environment_payload(settings: Any, metadata: dict[str, Any]) -> dict[str, Any]:
    extra = {
        k: v
        for k, v in sorted(metadata.items())
        if k not in ("soak_profile", "sample_transport_enabled", "manifest_extra")
    }
    return {
        "cwd": str(Path.cwd().resolve()),
        "metadata": extra,
        "pid": os.getpid(),
        "redis_enabled": bool(getattr(settings, "redis_enabled", False)),
        "sample_transport_enabled": bool(metadata.get("sample_transport_enabled", False)),
        "soak_profile": metadata.get("soak_profile"),
    }


@dataclass
class ArtifactCollection:
    files: dict[str, bytes] = field(default_factory=dict)
    missing_files: list[str] = field(default_factory=list)


def collect_runtime_artifacts(
    runtime_dir: Path,
    settings: Any,
    *,
    include_html: bool,
    metadata: dict[str, Any] | None = None,
) -> ArtifactCollection:
    """
    Assemble JSON payloads by reusing benchmark / integrity / bounded-state helpers.
    Optional disk artifacts: ``soak_report.json``, ``soak_report.html``, ``queue_pressure.json`` under ``runtime_dir``.
    """
    meta = dict(metadata or {})
    rd = str(runtime_dir.resolve())
    out = ArtifactCollection()
    rb = _load_runtime_benchmark_module()

    out.files["benchmark.json"] = _json_bytes(rb.build_benchmark_payload(settings))
    out.files["stability.json"] = _json_bytes(asyncio.run(rb.async_main(settings, sample_transport=False)))
    out.files["integrity.json"] = _json_bytes(_build_integrity_payload(rd))
    out.files["runtime_summary.json"] = _json_bytes(_build_runtime_summary_payload(rd, settings))
    out.files["environment.json"] = _json_bytes(_build_environment_payload(settings, meta))

    sj = _read_optional_file(runtime_dir / "soak_report.json")
    if sj is not None:
        out.files["soak_report.json"] = sj
    else:
        out.missing_files.append("soak_report.json")

    if include_html:
        html = _read_optional_file(runtime_dir / "soak_report.html")
        if html is not None:
            out.files["soak_report.html"] = html
        else:
            out.missing_files.append("soak_report.html")

    qp = _read_optional_file(runtime_dir / "queue_pressure.json")
    if qp is not None:
        out.files["queue_pressure.json"] = qp
    else:
        out.missing_files.append("queue_pressure.json")

    return out


def build_bundle_manifest(
    *,
    runtime_dir: str,
    included_files: dict[str, int],
    missing_files: list[str],
    git_sha: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = metadata or {}
    extra = meta.get("manifest_extra")
    manifest: dict[str, Any] = {
        "artifact_sizes": {k: included_files[k] for k in sorted(included_files)},
        "bundle_version": BUNDLE_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "git_sha": git_sha,
        "hostname": socket.gethostname(),
        "included_files": sorted(included_files.keys()),
        "missing_files": sorted(set(missing_files)),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "runtime_dir": runtime_dir,
        "total_size_bytes": int(sum(included_files.values())),
    }
    if isinstance(extra, dict):
        for k, v in sorted(extra.items()):
            if k not in manifest:
                manifest[str(k)] = v
    return manifest


def _finalize_manifest_bytes(
    *,
    runtime_dir: str,
    artifact_sizes: dict[str, int],
    missing_files: list[str],
    git_sha: str | None,
    metadata: dict[str, Any] | None,
) -> tuple[dict[str, Any], bytes]:
    """Include ``manifest.json`` byte length in ``artifact_sizes`` / ``total_size_bytes`` (fixed point)."""
    manifest: dict[str, Any] = {}
    raw = b""
    sizes = dict(artifact_sizes)
    for _ in range(8):
        manifest = build_bundle_manifest(
            runtime_dir=runtime_dir,
            included_files=sizes,
            missing_files=missing_files,
            git_sha=git_sha,
            metadata=metadata,
        )
        raw = _json_bytes(manifest)
        nlen = len(raw)
        if sizes.get("manifest.json") == nlen:
            break
        sizes = dict(artifact_sizes)
        sizes["manifest.json"] = nlen
    return manifest, raw


def write_runtime_bundle(
    runtime_dir: Path,
    output_zip: Path,
    settings: Any,
    *,
    include_html: bool = False,
    fail_on_missing: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Write a zip with top-level ``runtime_bundle/`` directory. Atomic replace on ``output_zip``.
    Returns the final manifest dict.
    """
    output_zip = output_zip.expanduser().resolve()
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    collection = collect_runtime_artifacts(runtime_dir, settings, include_html=include_html, metadata=metadata)

    if fail_on_missing and collection.missing_files:
        raise RuntimeError(f"missing optional artifacts: {collection.missing_files}")

    tmp_zip = output_zip.with_name(output_zip.name + ".tmp")
    rd = str(runtime_dir.resolve())
    manifest: dict[str, Any] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="newsroom_bundle_") as td:
            stage = Path(td) / BUNDLE_DIR_NAME
            stage.mkdir(parents=True)
            included_sizes: dict[str, int] = {}
            for name in sorted(collection.files.keys()):
                data = collection.files[name]
                (stage / name).write_bytes(data)
                included_sizes[name] = len(data)

            manifest, manifest_bytes = _finalize_manifest_bytes(
                runtime_dir=rd,
                artifact_sizes=dict(included_sizes),
                missing_files=collection.missing_files,
                git_sha=_git_sha_short(),
                metadata=metadata,
            )
            (stage / "manifest.json").write_bytes(manifest_bytes)

            if tmp_zip.is_file():
                tmp_zip.unlink()
            with zipfile.ZipFile(tmp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for fp in sorted(stage.rglob("*")):
                    if fp.is_file():
                        arc = f"{BUNDLE_DIR_NAME}/{fp.relative_to(stage).as_posix()}"
                        _zip_write_file(zf, fp, arc)
        os.replace(tmp_zip, output_zip)
    except Exception:
        if tmp_zip.is_file():
            try:
                tmp_zip.unlink()
            except OSError:
                pass
        raise

    return manifest


def bundle_summary_lines(output_zip: Path, manifest: dict[str, Any]) -> list[str]:
    return [
        f"bundle={output_zip}",
        f"files={len(manifest.get('included_files') or [])}",
        f"missing={len(manifest.get('missing_files') or [])}",
        f"total_size_bytes={manifest.get('total_size_bytes')}",
    ]
