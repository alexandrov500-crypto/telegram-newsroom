from __future__ import annotations

from collections.abc import Sequence


def compress_why_ranked(lines: Sequence[str], *, max_parts: int = 2) -> str:
    if not lines:
        return "Balanced editorial signals."
    return "; ".join(str(x) for x in lines[:max_parts])


def compress_priority_rationale(
    *,
    headline: str,
    urgency: str,
    why: Sequence[str],
    storyline_id: str | None,
    follow_up: str | None,
) -> str:
    bits: list[str] = []
    if why:
        bits.append(compress_why_ranked(why))
    if storyline_id and follow_up:
        bits.append(f"storyline {storyline_id} ({follow_up})")
    prefix = urgency.replace("-", " ").title()
    core = " · ".join(bits) if bits else headline[:80]
    return f"{prefix}: {core}"


def compress_editorial_item(
    *,
    pending_id: int,
    score: float,
    urgency: str,
    headline: str,
    why: Sequence[str],
    warnings: Sequence[str],
) -> str:
    line = f"#{pending_id} [{score:.2f}] {headline[:72]}"
    why_short = compress_why_ranked(why, max_parts=1)
    if why_short:
        line += f" — {why_short}"
    if warnings:
        line += f" ({warnings[0][:48]})"
    return line
