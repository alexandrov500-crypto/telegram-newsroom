"""Curated source registry — tier metadata and expansion path 3→25→40→120."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from db.models import SourceRegistryEntry
from db.session import session_scope

# Curated initial 25 (handles without @ for env compatibility)
CURATED_25: list[dict[str, str | int | float]] = [
    # macro
    {"handle": "cb_economics", "tier": "T0", "vertical": "macro", "poll_interval_sec": 300, "trust_score": 0.92},
    {"handle": "markets", "tier": "T1", "vertical": "macro", "poll_interval_sec": 600, "trust_score": 0.88},
    {"handle": "economist", "tier": "T2", "vertical": "macro", "poll_interval_sec": 900, "trust_score": 0.85},
    {"handle": "macro_alerts", "tier": "T2", "vertical": "macro", "poll_interval_sec": 900, "trust_score": 0.8},
    # finance
    {"handle": "finamalert", "tier": "T1", "vertical": "finance", "poll_interval_sec": 600, "trust_score": 0.86},
    {"handle": "investfundsru", "tier": "T2", "vertical": "finance", "poll_interval_sec": 900, "trust_score": 0.82},
    {"handle": "banksta", "tier": "T2", "vertical": "finance", "poll_interval_sec": 900, "trust_score": 0.8},
    {"handle": "stocksi", "tier": "T2", "vertical": "finance", "poll_interval_sec": 900, "trust_score": 0.78},
    # geopolitics
    {"handle": "rybar", "tier": "T1", "vertical": "geopolitics", "poll_interval_sec": 600, "trust_score": 0.84},
    {"handle": "meduzalive", "tier": "T2", "vertical": "geopolitics", "poll_interval_sec": 900, "trust_score": 0.83},
    {"handle": "bbbreaking", "tier": "T0", "vertical": "geopolitics", "poll_interval_sec": 300, "trust_score": 0.9},
    {"handle": "tass_agency", "tier": "T1", "vertical": "geopolitics", "poll_interval_sec": 600, "trust_score": 0.88},
    # crypto
    {"handle": "CoinDesk", "tier": "T1", "vertical": "crypto", "poll_interval_sec": 600, "trust_score": 0.87},
    {"handle": "whale_alert", "tier": "T2", "vertical": "crypto", "poll_interval_sec": 900, "trust_score": 0.82},
    {"handle": "DeFiIgnas", "tier": "T3", "vertical": "crypto", "poll_interval_sec": 1200, "trust_score": 0.75},
    {"handle": "cointelegraph", "tier": "T2", "vertical": "crypto", "poll_interval_sec": 900, "trust_score": 0.84},
    # energy
    {"handle": "oilpricecom", "tier": "T1", "vertical": "energy", "poll_interval_sec": 600, "trust_score": 0.86},
    {"handle": "energyworldnews", "tier": "T2", "vertical": "energy", "poll_interval_sec": 900, "trust_score": 0.8},
    {"handle": "gasworld", "tier": "T3", "vertical": "energy", "poll_interval_sec": 1200, "trust_score": 0.76},
    # corporate
    {"handle": "business", "tier": "T1", "vertical": "corporate", "poll_interval_sec": 600, "trust_score": 0.87},
    {"handle": "bloomberg", "tier": "T0", "vertical": "corporate", "poll_interval_sec": 300, "trust_score": 0.93},
    {"handle": "ReutersBiz", "tier": "T0", "vertical": "corporate", "poll_interval_sec": 300, "trust_score": 0.94},
    {"handle": "FT", "tier": "T1", "vertical": "corporate", "poll_interval_sec": 600, "trust_score": 0.91},
    {"handle": "WSJ", "tier": "T1", "vertical": "corporate", "poll_interval_sec": 600, "trust_score": 0.9},
    {"handle": "techcrunch", "tier": "T2", "vertical": "corporate", "poll_interval_sec": 900, "trust_score": 0.85},
]


@dataclass(frozen=True)
class SourceSpec:
    handle: str
    tier: str
    vertical: str
    poll_interval_sec: int
    trust_score: float


def _normalize_handle(h: str) -> str:
    return (h or "").strip().lstrip("@").lower()


def parse_source_channels_env(raw: str) -> list[str]:
    out: list[str] = []
    for part in (raw or "").split(","):
        h = part.strip()
        if h:
            out.append(h if h.startswith("@") else f"@{_normalize_handle(h)}")
    return out


async def seed_registry_if_empty() -> int:
    """Idempotent seed of curated 25 into source_registry."""
    now = datetime.now(UTC)
    inserted = 0
    async with session_scope() as session:
        existing = (await session.execute(select(SourceRegistryEntry.id).limit(1))).scalar_one_or_none()
        if existing is not None:
            return 0
        for row in CURATED_25:
            handle = _normalize_handle(str(row["handle"]))
            session.add(
                SourceRegistryEntry(
                    handle=handle,
                    tier=str(row["tier"]),
                    vertical=str(row["vertical"]),
                    poll_interval_sec=int(row["poll_interval_sec"]),
                    trust_score=float(row["trust_score"]),
                    status="active",
                    extras_json=json.dumps({"seed": "curated_25"}),
                    created_at=now,
                    updated_at=now,
                )
            )
            inserted += 1
    return inserted


async def load_active_source_handles(settings: Any) -> list[str]:
    """Merge env SOURCE_CHANNELS with registry (probation/disabled filtered)."""
    env_handles = {_normalize_handle(h) for h in settings.source_channels}
    async with session_scope() as session:
        rows = list(
            (await session.execute(select(SourceRegistryEntry).where(SourceRegistryEntry.status == "active"))).scalars()
        )
    registry = {_normalize_handle(r.handle) for r in rows if r.status == "active"}
    merged = env_handles | registry
    return [f"@{h}" for h in sorted(merged)]


def breaking_source_handles(settings: Any) -> list[str]:
    """T0 only — env override BREAKING_T0_SOURCES comma list else registry T0."""
    override = os.getenv("BREAKING_T0_SOURCES", "").strip()
    if override:
        return parse_source_channels_env(override)
    t0 = [_normalize_handle(str(r["handle"])) for r in CURATED_25 if str(r.get("tier")) == "T0"]
    env = {_normalize_handle(h) for h in settings.source_channels}
    handles = [h for h in t0 if h in env or os.getenv("SOURCE_REGISTRY_EXPAND", "false").lower() in ("1", "true", "yes")]
    return [f"@{h}" for h in handles] or [f"@{h}" for h in t0[:3]]


def shard_sources(handles: list[str], *, shard_id: int, shard_count: int) -> list[str]:
    if shard_count <= 1:
        return list(handles)
    ordered = sorted(handles, key=lambda h: _normalize_handle(h))
    return [h for i, h in enumerate(ordered) if i % shard_count == shard_id]


def tier_poll_interval_sec(tier: str) -> int:
    return {"T0": 300, "T1": 600, "T2": 900, "T3": 1200, "T4": 1800}.get(tier.upper(), 900)
