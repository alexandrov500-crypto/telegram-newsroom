from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.minimalism.compression import (
    build_compression_candidates,
    compute_architectural_compression_score,
)
from bot.editorial.flow_health.minimalism.continuity import (
    is_quiet_infrastructure_day,
    touch_quiet_infrastructure,
)
from bot.editorial.flow_health.minimalism.digest import build_minimalism_digest_lines
from bot.editorial.flow_health.minimalism.entropy import measure_operational_entropy
from bot.editorial.flow_health.minimalism.redundancy import detect_governance_redundancy


def minimalism_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Governance minimalism & architectural compression — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    cockpit = cockpit or gov.get("cockpit") or {}

    redundancy = detect_governance_redundancy(governance=gov, cockpit=cockpit)
    entropy = measure_operational_entropy(governance=gov, redundancy=redundancy, cockpit=cockpit)
    quiet = is_quiet_infrastructure_day(governance=gov, entropy=entropy)
    continuity = touch_quiet_infrastructure(quiet_today=quiet)
    compression = compute_architectural_compression_score(
        governance=gov,
        redundancy=redundancy,
        entropy=entropy,
        cockpit=cockpit,
        quiet_streak=int(continuity.get("quiet_infrastructure_streak_days") or 0),
    )
    candidates = build_compression_candidates(
        redundancy=redundancy,
        entropy=entropy,
        governance=gov,
    )

    sres = gov.get("strategic_resilience") or {}
    doc = gov.get("doctrine") or {}
    invisible = bool(
        sres.get("long_horizon_sustainability")
        and doc.get("institutional_stewardship_mode")
        and (gov.get("freeze_registry") or {}).get("ultra_quiet_digest")
        and compression.get("architectural_compression_band") in ("COMPRESSED", "MINIMALIST")
        and not entropy.get("entropy_elevated")
    )

    digest_lines = build_minimalism_digest_lines(
        compression=compression,
        entropy=entropy,
        continuity=continuity,
        compression_candidates=candidates,
        invisible_digest=invisible,
    )

    return {
        "redundancy": redundancy,
        "entropy": entropy,
        "compression": compression,
        "quiet_infrastructure": continuity,
        "compression_candidates": candidates,
        "compression_candidates_count": len(candidates),
        "invisible_digest_mode": invisible,
        "architectural_compression_score": compression.get("architectural_compression_score"),
        "architectural_compression_band": compression.get("architectural_compression_band"),
        "operational_entropy_accumulation": entropy.get("operational_entropy_accumulation"),
        "quiet_infrastructure_streak_days": continuity.get("quiet_infrastructure_streak_days"),
        "quiet_infrastructure_band": continuity.get("quiet_infrastructure_band"),
        "minimalism_digest_lines": digest_lines,
    }


__all__ = ["minimalism_snapshot"]
