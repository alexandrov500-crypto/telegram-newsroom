from __future__ import annotations

from collections.abc import Sequence

_ESCALATION_TERMS = (
    "surge",
    "surges",
    "escalat",
    "crisis",
    "emergency",
    "breaking",
    "shock",
    "plunge",
    "soar",
    "record",
    "unprecedented",
    "war",
    "invasion",
    "sanction",
    "ban",
    "halt",
    "default",
)

_DECEL_TERMS = ("ease", "cool", "slow", "stabiliz", "pause", "de-escalat")


def compute_storyline_momentum(
    *,
    headline: str,
    summary: str | None,
    publish_count: int,
    recent_headlines: Sequence[str],
    saturation: float,
) -> dict[str, float | str]:
    text = f"{headline} {summary or ''}".lower()
    escalation = sum(1 for t in _ESCALATION_TERMS if t in text)
    decel = sum(1 for t in _DECEL_TERMS if t in text)
    velocity = min(1.0, publish_count / 8.0)
    intensity = min(1.0, escalation * 0.18 - decel * 0.08 + 0.25)
    if recent_headlines and len(recent_headlines) >= 2:
        overlap = sum(
            1
            for h in recent_headlines[:3]
            if any(w in h.lower() for w in ("surge", "crisis", "war", "breaking"))
        )
        intensity = min(1.0, intensity + overlap * 0.12)
    momentum = max(0.0, min(1.0, intensity + velocity * 0.35 - saturation * 0.25))
    label = "stable"
    if momentum >= 0.72:
        label = "escalating"
    elif momentum >= 0.48:
        label = "building"
    elif momentum < 0.25:
        label = "fading"
    return {
        "storyline_momentum": round(momentum, 3),
        "momentum_label": label,
        "escalation_signals": escalation,
    }
