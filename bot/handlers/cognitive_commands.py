from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router

if TYPE_CHECKING:
    from bot.cognitive.runtime import CognitiveEditorialRuntime


def register_cognitive_handlers(
    *,
    cognitive_runtime: CognitiveEditorialRuntime | None,
) -> None:
    @router.message(Command("cognitive"))
    @admin_only("/cognitive")
    async def cmd_cognitive(message: Message) -> None:
        if cognitive_runtime is None:
            await message.answer("Cognitive runtime unavailable.")
            return
        budget = cognitive_runtime.repository.get_budget_state()
        agents = len(cognitive_runtime.agents.list_specs())
        await message.answer(
            f"Cognitive runtime\n"
            f"  policy: {cognitive_runtime.policy.policy_id} v{cognitive_runtime.policy.version}\n"
            f"  agents: {agents}\n"
            f"  budget: ${budget['daily_spend_usd']:.2f} / ${budget['daily_budget_usd']:.2f}"
        )

    @router.message(Command("evaluate"))
    @admin_only("/evaluate")
    async def cmd_evaluate(message: Message) -> None:
        if cognitive_runtime is None:
            await message.answer("Cognitive runtime unavailable.")
            return
        parts = (message.text or "").split(maxsplit=2)
        target_id = parts[1] if len(parts) > 1 else "manual"
        title = parts[2] if len(parts) > 2 else "Manual evaluation"
        results = await cognitive_runtime.evaluate_pending(
            target_type="pending_news",
            payload={
                "target_id": target_id,
                "title": title,
                "summary": title,
                "priority_score": 0.6,
                "source_count": 1,
            },
        )
        lines = ["Evaluation results:"]
        for r in results:
            lines.append(f"  {r}")
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("route_preview"))
    @admin_only("/route_preview")
    async def cmd_route_preview(message: Message) -> None:
        if cognitive_runtime is None:
            await message.answer("Cognitive runtime unavailable.")
            return
        from bot.cognitive.types import CognitiveContext

        text = (message.text or "").lower()
        if "breaking" in text:
            ctx = CognitiveContext(importance_score=0.95, qos_class="breaking", operation="summarize")
        else:
            ctx = CognitiveContext(importance_score=0.7, qos_class="digest", operation="summarize")
        decision = cognitive_runtime.router.route(ctx)
        await message.answer(
            f"Route preview\n"
            f"  model: {decision.model}\n"
            f"  strategy: {decision.strategy}\n"
            f"  depth: {decision.generation_depth}\n"
            f"  reason: {decision.reason}\n"
            f"  fallback: {', '.join(decision.fallback_chain)}"
        )

    @router.message(Command("predictions"))
    @admin_only("/predictions")
    async def cmd_predictions(message: Message) -> None:
        if cognitive_runtime is None:
            await message.answer("Cognitive runtime unavailable.")
            return
        forecasts = cognitive_runtime.repository.recent_forecasts(limit=8)
        if not forecasts:
            await message.answer("No recent predictions.")
            return
        lines = ["Recent predictions:"]
        for f in forecasts:
            lines.append(
                f"- {f['forecast_type']}: {f['predicted_value']:.2f} "
                f"(conf {f['confidence']:.2f}) — {f['explanation'][:60]}"
            )
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("cognitive_audit"))
    @admin_only("/cognitive_audit")
    async def cmd_cognitive_audit(message: Message) -> None:
        if cognitive_runtime is None:
            await message.answer("Cognitive runtime unavailable.")
            return
        rows = cognitive_runtime.repository.recent_cognitive_audit(limit=10)
        if not rows:
            await message.answer("No cognitive audit entries.")
            return
        lines = ["Cognitive audit:"]
        for r in rows:
            lines.append(f"- {r['action']}: {r['reason'][:80]}")
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("graph"))
    @admin_only("/graph")
    async def cmd_graph(message: Message) -> None:
        if cognitive_runtime is None:
            await message.answer("Cognitive runtime unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        node = parts[1] if len(parts) > 1 else "story:0"
        snap = cognitive_runtime.graph.snapshot(node)
        lines = [f"Graph @ {node}", f"  nodes: {len(snap.nodes)}", f"  edges: {len(snap.edges)}"]
        if snap.drift_alerts:
            lines.append(f"  drift: {', '.join(snap.drift_alerts)}")
        await message.answer("\n".join(lines)[:3900])
