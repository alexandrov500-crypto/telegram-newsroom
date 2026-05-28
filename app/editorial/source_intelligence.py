"""Dynamic source intelligence — wraps reputation store with publish-quality signals."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from utils.source_reputation import export_channel_scores_for_priority


@dataclass(frozen=True)
class SourceIntelProfile:
    channel: str
    tier_score: float
    approval_rate: float
    correction_rate: float
    duplicate_rate: float
    contradiction_signals: int
    misinformation_penalty: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def profile_channel(channel: str, *, runtime_dir: str | None = None) -> SourceIntelProfile:
    key = str(channel or "").strip().lower().lstrip("@")
    rep = export_channel_scores_for_priority(runtime_dir)
    row = rep.get(key) or rep.get(f"@{key}") or {}
    pub = int(row.get("publishes") or 0)
    rej = int(row.get("rejects") or 0)
    dup = int(row.get("duplicate_signals") or 0)
    corr = int(row.get("corrections") or 0)
    contra = int(row.get("contradictions") or 0)
    denom = max(1, pub + rej)
    dup_rate = dup / max(1, pub + dup)
    corr_rate = corr / max(1, pub)
    contra_rate = contra / max(1, pub)
    penalty = round(min(0.5, dup_rate * 0.2 + corr_rate * 0.25 + contra_rate * 0.3), 4)
    return SourceIntelProfile(
        channel=key,
        tier_score=float(row.get("score") or 0.35),
        approval_rate=round(pub / denom, 4),
        correction_rate=round(corr_rate, 4),
        duplicate_rate=round(dup_rate, 4),
        contradiction_signals=contra,
        misinformation_penalty=penalty,
    )


def top_sources(*, runtime_dir: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
    rep = export_channel_scores_for_priority(runtime_dir)
    rows: list[dict[str, Any]] = []
    for ch, row in rep.items():
        if not isinstance(row, dict):
            continue
        pub = int(row.get("publishes") or 0)
        if pub < 1:
            continue
        p = profile_channel(ch, runtime_dir=runtime_dir)
        rows.append({**p.to_dict(), "publishes": pub})
    rows.sort(key=lambda r: (float(r.get("tier_score") or 0), int(r.get("publishes") or 0)), reverse=True)
    return rows[:limit]
