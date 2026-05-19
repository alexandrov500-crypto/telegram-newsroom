from __future__ import annotations

from typing import Any


def build_minimalism_digest_lines(
    *,
    compression: dict[str, Any] | None = None,
    entropy: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
    compression_candidates: list[str] | None = None,
    invisible_digest: bool = False,
) -> list[str]:
    """Almost invisible digest at maturity — compression anomalies only."""
    lines: list[str] = []
    comp = compression or {}
    ent = entropy or {}
    cont = continuity or {}
    candidates = compression_candidates or []

    streak = int(cont.get("quiet_infrastructure_streak_days") or 0)
    band = comp.get("architectural_compression_band")

    if invisible_digest and band in ("COMPRESSED", "MINIMALIST") and not ent.get("entropy_elevated"):
        lines.append("Operational surface remains architecturally compressed")
        if streak >= 14:
            lines.append(f"Quiet infrastructure continuity stable for {streak}d")
        return lines[:2]

    if ent.get("entropy_elevated"):
        sig = (ent.get("entropy_signals") or ["entropy rising"])[0]
        lines.append(f"Architectural entropy: {sig.replace('_', ' ')}")

    if candidates and not invisible_digest:
        lines.append(candidates[0][:120])

    if band == "BLOATED" and not lines:
        lines.append(f"Compression score {comp.get('architectural_compression_score')} · consider advisory consolidation")

    return lines[:3]
