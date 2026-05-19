from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.handlers import admin_only, router

if TYPE_CHECKING:
    from bot.mesh.runtime import FederatedCognitiveMesh


def register_mesh_handlers(*, cognitive_mesh: FederatedCognitiveMesh | None) -> None:
    @router.message(Command("mesh"))
    @admin_only("/mesh")
    async def cmd_mesh(message: Message) -> None:
        if cognitive_mesh is None:
            await message.answer("Federated cognitive mesh unavailable.")
            return
        res = cognitive_mesh.repository.get_resilience()
        budget = cognitive_mesh.repository.get_budget(cognitive_mesh.region)
        leases = len(cognitive_mesh.repository.list_agent_leases(region=cognitive_mesh.region))
        await message.answer(
            f"Federated cognitive mesh\n"
            f"  node: {cognitive_mesh.node_id}\n"
            f"  region: {cognitive_mesh.region}\n"
            f"  health: {res['mesh_health']:.2f}\n"
            f"  agent leases: {leases}\n"
            f"  reasoning budget: {budget.get('spent_reasoning', 0):.0f}/"
            f"{budget.get('reasoning_quota', 100):.0f}"
        )

    @router.message(Command("mesh_agents"))
    @admin_only("/mesh_agents")
    async def cmd_mesh_agents(message: Message) -> None:
        if cognitive_mesh is None:
            await message.answer("Mesh unavailable.")
            return
        offers = cognitive_mesh.agents.marketplace()
        if not offers:
            await message.answer("No agents advertised in mesh.")
            return
        lines = ["Agent marketplace:"]
        for o in offers[:15]:
            lines.append(
                f"- {o.agent_id} @ {o.node_id} ({o.region}) caps={','.join(o.capabilities[:3])}"
            )
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("mesh_consensus"))
    @admin_only("/mesh_consensus")
    async def cmd_mesh_consensus(message: Message) -> None:
        if cognitive_mesh is None:
            await message.answer("Mesh unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        topic = parts[1] if len(parts) > 1 else "manual_review"
        session = cognitive_mesh.reasoning.open_session(topic)
        from bot.mesh.types import ConsensusVote

        cognitive_mesh.reasoning.submit_vote(
            session,
            ConsensusVote(
                node_id=cognitive_mesh.node_id,
                vote=0.75,
                confidence=0.9,
                reason="operator-initiated baseline vote",
            ),
        )
        result = cognitive_mesh.reasoning.finalize(session)
        try:
            from bot.observability.metrics import record_mesh_consensus

            record_mesh_consensus(completed=True)
        except Exception:
            pass
        await message.answer(
            f"Consensus session {result.session_id}\n"
            f"  score: {result.consensus_score:.3f}\n"
            f"  confidence: {result.confidence:.3f}\n"
            f"  {result.explanation}"
        )

    @router.message(Command("mesh_explain"))
    @admin_only("/mesh_explain")
    async def cmd_mesh_explain(message: Message) -> None:
        if cognitive_mesh is None:
            await message.answer("Mesh unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        session_id = parts[1] if len(parts) > 1 else ""
        if not session_id:
            await message.answer("Usage: /mesh_explain <session_id>")
            return
        text = cognitive_mesh.observability.explain_conclusion(session_id)
        await message.answer(text[:3900])

    @router.message(Command("mesh_tournament"))
    @admin_only("/mesh_tournament")
    async def cmd_mesh_tournament(message: Message) -> None:
        if cognitive_mesh is None:
            await message.answer("Mesh unavailable.")
            return
        result = await cognitive_mesh.simulation.run_tournament(
            ["policy_eval", "routing_ab"],
            lane="mesh_shadow",
            seed=42,
        )
        await message.answer(
            f"Tournament {result.tournament_id}\n"
            f"  winner: {result.winner}\n"
            f"  passed: {result.passed}\n"
            f"  scores: {result.scores}"
        )
