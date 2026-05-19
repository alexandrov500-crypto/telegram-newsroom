from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router

if TYPE_CHECKING:
    from bot.epistemic.runtime import EpistemicIntegrityLayer


def register_epistemic_handlers(*, epistemic_layer: EpistemicIntegrityLayer | None) -> None:
    @router.message(Command("epistemic"))
    @admin_only("/epistemic")
    async def cmd_epistemic(message: Message) -> None:
        if epistemic_layer is None:
            await message.answer("Epistemic integrity layer unavailable.")
            return
        snap = epistemic_layer.observability.build_snapshot()
        await message.answer(
            f"Epistemic integrity\n"
            f"  stability: {snap.federation_stability:.2f}\n"
            f"  misinfo pressure: {snap.misinformation_pressure:.2f}\n"
            f"  open contradictions: {len(snap.contradiction_network)}"
        )

    @router.message(Command("confidence"))
    @admin_only("/confidence")
    async def cmd_confidence(message: Message) -> None:
        if epistemic_layer is None:
            await message.answer("Epistemic layer unavailable.")
            return
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 2:
            await message.answer("Usage: /confidence <type> <id>")
            return
        text = epistemic_layer.calibration.explain_confidence_lineage(parts[1], parts[2] if len(parts) > 2 else "manual")
        await message.answer(text[:3900])

    @router.message(Command("contradictions"))
    @admin_only("/contradictions")
    async def cmd_contradictions(message: Message) -> None:
        if epistemic_layer is None:
            await message.answer("Epistemic layer unavailable.")
            return
        text = epistemic_layer.calibration.explore_contradictions()
        await message.answer(text[:3900])

    @router.message(Command("trust"))
    @admin_only("/trust")
    async def cmd_trust(message: Message) -> None:
        if epistemic_layer is None:
            await message.answer("Epistemic layer unavailable.")
            return
        parts = (message.text or "").split()
        if len(parts) < 4:
            await message.answer("Usage: /trust <from> <to> <score_0_to_1>")
            return
        try:
            score = float(parts[3])
        except ValueError:
            await message.answer("Invalid score.")
            return
        epistemic_layer.calibration.override_trust(
            parts[1], parts[2], score, operator_id=str(message.from_user.id), reason="operator command",
        )
        await message.answer(f"Trust updated: {parts[1]} → {parts[2]} = {score:.2f}")

    @router.message(Command("analyze_story"))
    @admin_only("/analyze_story")
    async def cmd_analyze_story(message: Message) -> None:
        if epistemic_layer is None:
            await message.answer("Epistemic layer unavailable.")
            return
        parts = (message.text or "").split(maxsplit=2)
        story_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        title = parts[2] if len(parts) > 2 else "Manual story analysis"
        result = await epistemic_layer.analyze_story(
            story_id=story_id,
            title=title,
            summary=title,
            source="operator",
            source_count=1,
        )
        lines = [f"Epistemic analysis for story {story_id}:"]
        if result.get("epistemic_score"):
            es = result["epistemic_score"]
            lines.append(f"  confidence: {es.get('confidence', 0):.2f} uncertainty: {es.get('uncertainty', 0):.2f}")
        if result.get("narrative"):
            n = result["narrative"]
            lines.append(f"  framing: {n.get('framing', [])} anomaly: {n.get('anomaly', 0):.2f}")
        if result.get("alert"):
            lines.append(f"  alert: {result['alert']}")
        await message.answer("\n".join(lines)[:3900])
