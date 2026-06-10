"""UEOS layer conflict arbitration — final arbiter above Stability, EGDL, AUH."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class LayerConflict(str, Enum):
    STABILITY_VS_EGDL = "stability_vs_egdl"
    AUH_VS_EGDL = "auh_vs_egdl"
    ANTI_PAUSE_VS_REJECTION = "anti_pause_vs_rejection"
    LOW_SIGNAL_COMPRESSION = "low_signal_compression"
    AUDIENCE_REPLACEMENT = "audience_replacement"
    CONTENT_PRINCIPLE = "content_principle"


@dataclass(frozen=True)
class LayerArbitration:
    winner: str
    conflicts_resolved: tuple[str, ...]
    stability_override: bool
    auh_wins_over_gravity: bool
    compression_required: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "conflicts_resolved": list(self.conflicts_resolved),
            "stability_override": self.stability_override,
            "auh_wins_over_gravity": self.auh_wins_over_gravity,
            "compression_required": self.compression_required,
            "reason": self.reason,
        }


def arbitrate_layer_conflicts(
    *,
    anti_pause_active: bool,
    publishing_mode: str,
    gravity_total: float,
    crs_total: float,
    ues_total: float,
    dominance_reject: bool,
    auh_reject: bool,
    cluster_size: int,
    quality_score: float,
    replaces_channels: bool,
) -> LayerArbitration:
    conflicts: list[str] = []
    stability_override = False
    auh_wins = False
    compression = False
    winner = "ueos"

    if anti_pause_active and (dominance_reject or auh_reject):
        conflicts.append(LayerConflict.ANTI_PAUSE_VS_REJECTION.value)
        stability_override = True
        winner = "stability"

    if crs_total > gravity_total + 5:
        conflicts.append(LayerConflict.AUH_VS_EGDL.value)
        auh_wins = True
        if not stability_override:
            winner = "auh"

    if anti_pause_active and gravity_total < 55 and publishing_mode != "core":
        conflicts.append(LayerConflict.STABILITY_VS_EGDL.value)
        stability_override = True
        winner = "stability"

    low_signal = cluster_size >= 2 and quality_score < 52 and crs_total < 65
    if low_signal or (cluster_size >= 3 and crs_total < 70):
        conflicts.append(LayerConflict.LOW_SIGNAL_COMPRESSION.value)
        compression = True
        if not stability_override:
            winner = "auh"

    if not replaces_channels and ues_total < 70:
        conflicts.append(LayerConflict.AUDIENCE_REPLACEMENT.value)
        compression = compression or cluster_size >= 2

    return LayerArbitration(
        winner=winner,
        conflicts_resolved=tuple(conflicts),
        stability_override=stability_override,
        auh_wins_over_gravity=auh_wins,
        compression_required=compression,
        reason=conflicts[-1] if conflicts else "ueos_default",
    )
