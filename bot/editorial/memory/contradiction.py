from __future__ import annotations

_DIRECTION_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("easing", ("cool", "cools", "slow", "slows", "ease", "easing", "soften", "decline", "falls")),
    ("rising", ("rise", "rises", "surge", "surges", "accelerat", "heat", "hotter", "spike", "jump")),
    ("rally", ("rally", "rallies", "gain", "gains", "climb", "rebound", "soar", "jump")),
    ("slump", ("slump", "fall", "falls", "drop", "drops", "selloff", "tumble", "plunge", "decline")),
)


def detect_tone_direction(text: str) -> str | None:
    lower = (text or "").lower()
    hits: list[str] = []
    for direction, needles in _DIRECTION_GROUPS:
        if any(n in lower for n in needles):
            hits.append(direction)
    if not hits:
        return None
    if "easing" in hits and "rising" in hits:
        return "mixed"
    if "rally" in hits and "slump" in hits:
        return "mixed"
    return hits[0]


def detect_contradictions(
    *,
    prior_text: str | None,
    prior_tone: str | None,
    new_text: str,
) -> list[str]:
    flags: list[str] = []
    new_tone = detect_tone_direction(new_text)
    if prior_tone and new_tone and prior_tone != new_tone:
        opposing = {
            ("easing", "rising"),
            ("rising", "easing"),
            ("rally", "slump"),
            ("slump", "rally"),
        }
        if (prior_tone, new_tone) in opposing or (new_tone, prior_tone) in opposing:
            flags.append(f"tone_shift:{prior_tone}_to_{new_tone}")

    if prior_text:
        prior_dir = detect_tone_direction(prior_text)
        if prior_dir and new_tone and prior_dir != new_tone and prior_dir != "mixed":
            if {prior_dir, new_tone} in ({"easing", "rising"}, {"rally", "slump"}):
                flags.append("framing_conflict")

    inflation_easing = any(w in new_text.lower() for w in ("easing", "cools", "slows"))
    inflation_rising = any(w in new_text.lower() for w in ("accelerat", "surges", "heats"))
    if prior_text:
        prior_easing = any(w in prior_text.lower() for w in ("easing", "cools", "slows"))
        prior_rising = any(w in prior_text.lower() for w in ("accelerat", "surges", "heats"))
        if prior_easing and inflation_rising:
            flags.append("inflation_direction_conflict")
        if prior_rising and inflation_easing:
            flags.append("inflation_direction_conflict")

    return flags
