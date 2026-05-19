from __future__ import annotations

from typing import Any


def build_resilience_digest_lines(
    *,
    resilience: dict[str, Any] | None = None,
    horizon: dict[str, Any] | None = None,
    erosion: dict[str, Any] | None = None,
    fatigue: dict[str, Any] | None = None,
    long_horizon: bool = False,
    ultra_quiet: bool = False,
) -> list[str]:
    """Mature infrastructure steward — not sustainability dashboard."""
    lines: list[str] = []
    res = resilience or {}
    hor = horizon or {}
    eros = erosion or {}
    fat = fatigue or {}

    band = res.get("strategic_resilience_band")
    hor_band = hor.get("sustainability_horizon_band")

    if long_horizon and ultra_quiet and not eros.get("architectural_erosion_detected"):
        lines.append(f"Strategic resilience remains {band or 'LONG_HORIZON'}")
        lines.append("Architectural erosion remains minimal across stewardship horizon")
        return lines[:3]

    if eros.get("architectural_erosion_detected"):
        sig = (eros.get("erosion_signals") or ["erosion"])[0]
        lines.append(f"Architectural erosion signal: {sig.replace('_', ' ')}")
        if fat.get("stewardship_fatigue_detected"):
            lines.append("Stewardship fatigue may affect long-horizon sustainability")
    elif band not in (None, "LONG_HORIZON", "RESILIENT"):
        lines.append(
            f"Strategic resilience {res.get('strategic_resilience_index')} · {band}",
        )

    if hor_band and hor_band not in ("LONG", "INSTITUTIONAL_LONG_HORIZON") and not ultra_quiet:
        lines.append(f"Sustainability horizon ~{hor.get('sustainability_horizon_days')}d ({hor_band})")

    if fat.get("intervention_dependency_rising") and not eros.get("architectural_erosion_detected"):
        lines.append("Intervention dependency rising — monitor sustainability")

    return lines[:4]
