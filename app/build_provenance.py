"""Docker/build provenance metadata (no secrets)."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

RUNTIME_STARTED_AT_UNIX: float = time.time()
RUNTIME_STARTED_AT_ISO: str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(RUNTIME_STARTED_AT_UNIX))


@dataclass(frozen=True, slots=True)
class BuildProvenance:
    git_sha: str
    build_timestamp: str
    build_branch: str
    build_version: str

    def to_dict(self) -> dict[str, str]:
        return {
            "git_sha": self.git_sha,
            "build_timestamp": self.build_timestamp,
            "build_branch": self.build_branch,
            "build_version": self.build_version,
        }


def load_build_provenance() -> BuildProvenance:
    return BuildProvenance(
        git_sha=(
            os.getenv("NEWSROOM_GIT_SHA", "").strip()
            or os.getenv("GIT_SHA", "").strip()
            or "unknown"
        )[:40],
        build_timestamp=(
            os.getenv("NEWSROOM_BUILD_TIMESTAMP", "").strip()
            or os.getenv("BUILD_TIMESTAMP", "").strip()
            or "unknown"
        )[:64],
        build_branch=(
            os.getenv("NEWSROOM_BUILD_BRANCH", "").strip()
            or os.getenv("BUILD_BRANCH", "").strip()
            or "unknown"
        )[:128],
        build_version=(
            os.getenv("NEWSROOM_BUILD_VERSION", "").strip()
            or os.getenv("BUILD_VERSION", "").strip()
            or os.getenv("NEWSROOM_APP_VERSION", "").strip()
            or "unknown"
        )[:64],
    )


def version_payload(*, polling_instance_id: str = "") -> dict[str, Any]:
    prov = load_build_provenance()
    return {
        **prov.to_dict(),
        "runtime_started_at": RUNTIME_STARTED_AT_ISO,
        "runtime_started_at_unix": RUNTIME_STARTED_AT_UNIX,
        "polling_instance_id": polling_instance_id,
    }
