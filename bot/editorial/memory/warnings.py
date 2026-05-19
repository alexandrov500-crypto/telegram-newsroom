from __future__ import annotations

from bot.editorial.memory.types import (
    FOLLOW_UP_DUPLICATE,
    FOLLOW_UP_MINOR,
    EditorialMemoryReport,
)


def build_memory_warnings(report: EditorialMemoryReport) -> tuple[str, ...]:
    warnings: list[str] = []
    if report.follow_up_kind == FOLLOW_UP_DUPLICATE:
        warnings.append("duplicate narrative — very similar to recent storyline post")
    elif report.follow_up_kind == FOLLOW_UP_MINOR:
        warnings.append("minor variation — limited new information vs recent post")

    if report.saturation_score >= 0.65:
        warnings.append("storyline saturation high — audience may be fatigued")

    if report.contradiction_flags:
        warnings.append("framing differs significantly from recent storyline tone")

    if report.match_score >= 0.5 and not report.context_snippet:
        warnings.append("missing continuity — consider a brief follow-up frame")

    if report.follow_up_kind == "new_development" and report.publish_count >= 3:
        warnings.append("new angle on heavily covered storyline — ensure novelty")

    seen: set[str] = set()
    unique: list[str] = []
    for w in warnings:
        key = w.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(w)
    return tuple(unique[:6])
