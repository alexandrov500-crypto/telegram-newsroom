"""Autonomous source curation — promote high-yield handles to fastlane."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from db.models import SourceRegistryEntry
from db.session import session_scope


def source_curation_enabled() -> bool:
    return os.getenv("AUTONOMOUS_SOURCE_CURATION_ENABLED", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _curation_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / "autonomous_fastlane_sources.json"


def _yield_min_promote() -> float:
    try:
        return float(os.getenv("AUTONOMOUS_SOURCE_YIELD_PROMOTE_MIN", "0.42"))
    except ValueError:
        return 0.42


def _yield_max_demote() -> float:
    try:
        return float(os.getenv("AUTONOMOUS_SOURCE_YIELD_DEMOTE_MAX", "0.16"))
    except ValueError:
        return 0.16


def _max_fastlane() -> int:
    try:
        return max(3, min(12, int(os.getenv("AUTONOMOUS_SOURCE_FASTLANE_MAX", "8"))))
    except ValueError:
        return 8


async def curate_fastlane_sources(
    runtime_dir: str,
    *,
    env_baseline: list[str] | None = None,
) -> dict[str, Any]:
    """
    Merge env baseline with top yield sources into fastlane list.
    Demotes chronic low-yield handles from fastlane (not from collect list).
    """
    baseline = [h.strip().lstrip("@").lower() for h in (env_baseline or []) if h.strip()]
    promoted: list[dict[str, Any]] = []
    demoted: list[str] = []

    if not source_curation_enabled():
        payload = {
            "updated_at": datetime.now(UTC).isoformat(),
            "enabled": False,
            "fastlane": [f"@{h}" for h in baseline],
        }
        _curation_path(runtime_dir).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload

    async with session_scope() as session:
        rows = list((await session.execute(select(SourceRegistryEntry))).scalars().all())

    ranked: list[tuple[str, float, int, str]] = []
    for row in rows:
        if row.status not in {"active", "probation"}:
            continue
        try:
            ex = json.loads(row.extras_json or "{}")
        except (json.JSONDecodeError, TypeError):
            ex = {}
        y = float(ex.get("yield_score") or 0.0)
        posts = int(ex.get("yield_posts") or 0)
        handle = (row.handle or "").strip().lower().lstrip("@")
        if not handle:
            continue
        ranked.append((handle, y, posts, row.tier))

    ranked.sort(key=lambda x: (x[1], x[2]), reverse=True)

    fastlane_set: set[str] = set(baseline)
    promote_min = _yield_min_promote()
    demote_max = _yield_max_demote()

    for handle, y, posts, tier in ranked:
        if len(fastlane_set) >= _max_fastlane():
            break
        if y >= promote_min and posts >= 2:
            if handle not in fastlane_set:
                promoted.append({"handle": handle, "yield_score": y, "tier": tier})
            fastlane_set.add(handle)

    for handle, y, posts, _tier in ranked:
        if handle in baseline:
            continue
        if posts >= 6 and y <= demote_max and handle in fastlane_set:
            fastlane_set.discard(handle)
            demoted.append(handle)

    fastlane = sorted(f"@{h}" for h in fastlane_set)

    payload = {
        "updated_at": datetime.now(UTC).isoformat(),
        "enabled": True,
        "fastlane": fastlane,
        "promoted": promoted[:8],
        "demoted": demoted,
        "yield_promote_min": promote_min,
    }
    path = _curation_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def load_autonomous_fastlane_handles(runtime_dir: str) -> frozenset[str]:
    if not source_curation_enabled():
        return frozenset()
    try:
        data = json.loads(_curation_path(runtime_dir).read_text(encoding="utf-8"))
        handles = data.get("fastlane") if isinstance(data.get("fastlane"), list) else []
        out: set[str] = set()
        for h in handles:
            key = str(h).strip().lower()
            if not key:
                continue
            out.add(key if key.startswith("@") else f"@{key.lstrip('@')}")
            out.add(key.lstrip("@"))
        return frozenset(out)
    except (OSError, json.JSONDecodeError):
        return frozenset()
