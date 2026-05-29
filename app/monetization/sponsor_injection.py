"""Sponsor injection — native, brand-safe ad placement."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from db.models import SponsorSlot
from db.session import session_scope


_FORBIDDEN_SPONSOR_CONTEXT = re.compile(
    r"(войн|war|death|смерт|теракт|attack|sanction|санкц|bankruptcy|дефолт|"
    r"tragedy|катастроф|crash\s+fatal|child)",
    re.I,
)

_SPONSOR_MARKER = "— партнёрский материал"


@dataclass(frozen=True)
class SponsorInjectionResult:
    content: str
    injected: bool
    slot_key: str
    safety_score: float
    reason: str


def _enabled() -> bool:
    return os.getenv("W5_SPONSOR_INJECTION_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def score_sponsor_safety(content: str, *, vertical: str = "general") -> float:
    t = (content or "").strip()
    if not t:
        return 0.0
    score = 0.7
    if _FORBIDDEN_SPONSOR_CONTEXT.search(t):
        score -= 0.45
    if _SPONSOR_MARKER in t:
        score -= 0.3
    if len(t) < 120:
        score -= 0.15
    return round(max(0.0, min(1.0, score)), 4)


async def pick_sponsor_slot(*, vertical: str = "general") -> SponsorSlot | None:
    async with session_scope() as session:
        rows = list(
            (
                await session.execute(
                    select(SponsorSlot).where(SponsorSlot.active == 1).order_by(SponsorSlot.cpm_usd.desc())
                )
            ).scalars()
        )
    for row in rows:
        if int(row.used_today or 0) >= int(row.daily_cap or 2):
            continue
        try:
            verts = json.loads(row.verticals_json or "[]")
        except (json.JSONDecodeError, TypeError):
            verts = []
        if not verts or vertical in verts or "general" in verts:
            return row
    return None


def _default_slot_copy(vertical: str) -> str:
    link = os.getenv("W5_SPONSOR_DEFAULT_LINK", "").strip()
    label = os.getenv("W5_SPONSOR_DEFAULT_LABEL", "Market intelligence tools").strip()
    if link:
        return f"\n\n{_SPONSOR_MARKER}: {label} → {link}"
    return f"\n\n{_SPONSOR_MARKER}: {label}"


def inject_sponsor_block(content: str, *, slot: SponsorSlot | None, vertical: str = "general") -> SponsorInjectionResult:
    safety = score_sponsor_safety(content, vertical=vertical)
    min_safety = float(os.getenv("W5_SPONSOR_MIN_SAFETY", "0.62"))
    if safety < min_safety:
        return SponsorInjectionResult(content, False, "", safety, "unsafe_context")

    template = (slot.copy_template if slot and slot.copy_template else _default_slot_copy(vertical)).strip()
    if not template:
        return SponsorInjectionResult(content, False, "", safety, "no_slot")

    block = template if template.startswith("\n") else f"\n\n{template}"
    if _SPONSOR_MARKER not in block and "партнёр" not in block.lower():
        block = f"\n\n{_SPONSOR_MARKER}{block}"

    return SponsorInjectionResult(
        content=(content or "").rstrip() + block,
        injected=True,
        slot_key=str(slot.slot_key if slot else "default"),
        safety_score=safety,
        reason="ok",
    )


async def record_sponsor_use(slot_key: str) -> None:
    async with session_scope() as session:
        row = (
            await session.execute(select(SponsorSlot).where(SponsorSlot.slot_key == slot_key))
        ).scalar_one_or_none()
        if row is None:
            return
        row.used_today = int(row.used_today or 0) + 1
        row.updated_at = datetime.now(UTC)


async def reset_daily_sponsor_caps() -> int:
    """Reset used_today on all slots — run at day boundary."""
    async with session_scope() as session:
        rows = list((await session.execute(select(SponsorSlot))).scalars())
        for row in rows:
            row.used_today = 0
            row.updated_at = datetime.now(UTC)
    return len(rows)
