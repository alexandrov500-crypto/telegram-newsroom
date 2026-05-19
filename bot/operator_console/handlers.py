from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from aiogram import F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.handlers import admin_only, router
from bot.operator_console.context import get_operator_console
from bot.operator_console.explain import (
    explain_story,
    story_lineage,
    trust_story,
    why_flagged,
)
from bot.operator_console.formatting import split_message
from bot.staging.context import get_publish_guard

if TYPE_CHECKING:
    from bot.distributed.cluster.coordinator import ClusterCoordinator
    from bot.editorial.agent_service import EditorialAgentService
    from bot.epistemic.runtime import EpistemicIntegrityLayer
    from bot.mesh.runtime import FederatedCognitiveMesh
    from bot.operations.runtime import OperationsPlatform
    from bot.publisher import ChannelPublisher
    from bot.publishing.channel_router import ChannelRouter
    from bot.runtime.autonomous_runtime import AutonomousRuntime
    from bot.storage.cluster_repository import ClusterRepository
    from bot.storage.coordination_repository import CoordinationRepository
    from bot.storage.editorial_repository import EditorialRepository
    from bot.editorial.publish_flow import publish_pending_item

logger = logging.getLogger(__name__)


def register_operator_console_handlers(
    *,
    editorial: EditorialRepository,
    clusters: ClusterRepository,
    publisher: ChannelPublisher,
    channel_router: ChannelRouter | None,
    epistemic_layer: EpistemicIntegrityLayer | None,
    cognitive_mesh: FederatedCognitiveMesh | None,
    operations_platform: OperationsPlatform | None,
    coordination: CoordinationRepository | None,
    cluster_coordinator: ClusterCoordinator | None,
    autonomous_runtime: object | None,
    agents: EditorialAgentService | None,
    node_id: str,
    link_dedup: object | None = None,
    sources: object | None = None,
    entities: object | None = None,
    analytics: object | None = None,
    localizations: object | None = None,
    adaptive: object | None = None,
    publish_idempotency: object | None = None,
) -> None:
    async def _answer_long(message: Message, text: str) -> None:
        for chunk in split_message(text):
            await message.answer(chunk, parse_mode="HTML")

    @router.message(Command("topology_live"))
    @admin_only("/topology_live")
    async def cmd_topology_live(message: Message) -> None:
        lines = ["<b>🌐 Topology live</b>"]
        if autonomous_runtime is not None and coordination is not None:
            try:
                topo = autonomous_runtime.topology.build_snapshot(
                    coordination=coordination,
                    leader=cluster_coordinator.current_leader() if cluster_coordinator else None,
                )
                lines.append(
                    f"Health: {topo.health_score:.2f} · nodes={len(topo.nodes)} "
                    f"partitions={len(topo.partitions)}"
                )
                for n in topo.nodes[:8]:
                    lines.append(
                        f"• {escape_node(str(n.get('node_id', '?')))} "
                        f"{n.get('region', '?')} health={float(n.get('health_score', 0)):.2f}"
                    )
            except Exception as exc:
                lines.append(f"Topology: {exc}")
        else:
            lines.append("Autonomous runtime unavailable.")
        if coordination is not None:
            nodes = coordination.list_nodes(include_stale=False)
            leader = coordination.current_leader()
            lines.append(f"\nLeader: <code>{leader or 'none'}</code>")
            lines.append(f"Registered: {len(nodes)}")
        await _answer_long(message, "\n".join(lines))

    @router.message(Command("mesh_live"))
    @admin_only("/mesh_live")
    async def cmd_mesh_live(message: Message) -> None:
        if cognitive_mesh is None:
            await message.answer("Mesh unavailable.")
            return
        res = cognitive_mesh.repository.get_resilience()
        budget = cognitive_mesh.repository.get_budget(cognitive_mesh.region)
        lines = [
            "<b>🕸 Mesh live</b>",
            f"Health: <b>{float(res.get('mesh_health', 0)):.2f}</b>",
            f"Gossip pressure: {float(res.get('gossip_pressure', 0)):.2f}",
            f"Reasoning: {budget.get('spent_reasoning', 0):.0f}/"
            f"{budget.get('reasoning_quota', 100):.0f}",
            f"Region: {cognitive_mesh.region}",
        ]
        await _answer_long(message, "\n".join(lines))

    @router.message(Command("runtime_live"))
    @admin_only("/runtime_live")
    async def cmd_runtime_live(message: Message) -> None:
        from bot.runtime.state import runtime_state

        backlog = 0
        if operations_platform is not None:
            try:
                from bot.observability.registry import ObservabilityRegistry

                backlog = 0
            except Exception:
                pass
        lines = [
            "<b>⚙️ Runtime live</b>",
            f"Mode: {runtime_state.operational_mode}",
            f"Staging: {runtime_state.staging_mode}",
            f"Shadow publish: {runtime_state.shadow_publish_only}",
            f"Queue backlog: {backlog}",
            f"Published session: {runtime_state.published_count}",
            f"Skipped: {runtime_state.skipped_count}",
        ]
        from bot.reliability.context_holder import get_reliability

        rel = get_reliability()
        if rel is not None and rel.health.last_snapshot is not None:
            snap = rel.health.last_snapshot
            lines.append(
                f"Health: {snap.overall_state.value} ({snap.health_score:.2f}) · "
                f"publish {snap.publish_mode.value}",
            )
        if cluster_coordinator is not None:
            lines.append(f"Leader: {cluster_coordinator.current_leader() or 'none'}")
        await _answer_long(message, "\n".join(lines))

    @router.message(Command("contradiction_details"))
    @admin_only("/contradiction_details")
    async def cmd_contradiction_details(message: Message) -> None:
        if epistemic_layer is None:
            await message.answer("Epistemic layer unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /contradiction_details <contradiction_id>")
            return
        cid = parts[1].strip()
        rows = epistemic_layer.contradictions.lineage(cid)
        if not rows:
            await message.answer(f"No contradiction `{cid}` found.")
            return
        lines = [f"<b>Contradiction {cid}</b>"]
        for r in rows[:12]:
            lines.append(f"• {r}")
        await _answer_long(message, "\n".join(lines))

    @router.message(Command("resolve_contradiction"))
    @admin_only("/resolve_contradiction")
    async def cmd_resolve_contradiction(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /resolve_contradiction <contradiction_id>")
            return
        cid = parts[1].strip()
        if epistemic_layer is None:
            await message.answer("Epistemic layer unavailable.")
            return
        with epistemic_layer.repository._connect() as conn:
            conn.execute(
                "UPDATE epistemic_contradictions SET status = 'resolved' WHERE contradiction_id = ?",
                (cid,),
            )
            conn.commit()
        await message.answer(f"✅ Contradiction <code>{cid}</code> marked resolved.")

    @router.message(Command("explain_story"))
    @admin_only("/explain_story")
    async def cmd_explain_story(message: Message) -> None:
        news_id = _parse_id(message, "/explain_story")
        if news_id is None:
            await message.answer("Usage: /explain_story <id>")
            return
        text = explain_story(
            editorial=editorial,
            clusters=clusters,
            epistemic=epistemic_layer,
            news_id=news_id,
        )
        await _answer_long(message, text)

    @router.message(Command("story_lineage"))
    @admin_only("/story_lineage")
    async def cmd_story_lineage(message: Message) -> None:
        news_id = _parse_id(message, "/story_lineage")
        if news_id is None:
            await message.answer("Usage: /story_lineage <id>")
            return
        await _answer_long(message, story_lineage(editorial=editorial, news_id=news_id, node_id=node_id))

    @router.message(Command("trust_story"))
    @admin_only("/trust_story")
    async def cmd_trust_story(message: Message) -> None:
        news_id = _parse_id(message, "/trust_story")
        if news_id is None:
            await message.answer("Usage: /trust_story <id>")
            return
        item = editorial.get_by_id(news_id)
        if item is None:
            await message.answer("Story not found.")
            return
        await _answer_long(
            message,
            trust_story(epistemic=epistemic_layer, source=item.source),
        )

    @router.message(Command("ops_score"))
    @admin_only("/ops_score")
    async def cmd_ops_score(message: Message) -> None:
        from bot.operator_console.context import get_operator_console
        from bot.operator_console.scoring import compute_ops_health

        console = get_operator_console()
        if console is None:
            await message.answer("Operator console unavailable.")
            return
        open_c = 0
        mesh_h = 1.0
        epistab = 1.0
        if operations_platform is not None:
            open_c = operations_platform.repository.open_contradiction_count()
        if cognitive_mesh is not None:
            mesh_h = float(cognitive_mesh.repository.get_resilience().get("mesh_health", 1.0))
        if epistemic_layer is not None:
            snap = epistemic_layer.repository.latest_snapshot("integrity_full")
            if snap:
                epistab = float(snap.get("federation_stability", 1.0))
        fatigue = console.hub.fatigue.snapshot()
        health = compute_ops_health(
            queue_backlog=0,
            mesh_health=mesh_h,
            epistemic_stability=epistab,
            open_contradictions=open_c,
            fatigue_score=fatigue.score,
        )
        await _answer_long(message, health.summary_text())

    @router.message(Command("approval_queue"))
    @admin_only("/approval_queue")
    async def cmd_approval_queue(message: Message) -> None:
        from bot.operator_console.context import get_operator_console

        console = get_operator_console()
        if console is None:
            await message.answer("Operator console unavailable.")
            return
        pending = console.hub.approval_queue.pending_count()
        await message.answer(f"Pending approvals: <b>{pending}</b>\nFlushing queue…", parse_mode="HTML")
        await console.flush_pending_signals()

    @router.message(Command("incidents"))
    @admin_only("/incidents")
    async def cmd_incidents(message: Message) -> None:
        from bot.operator_console.context import get_operator_console

        console = get_operator_console()
        if console is None:
            await message.answer("Operator console unavailable.")
            return
        threads = list(console.hub.incidents._threads.values())
        if not threads:
            await message.answer(
                "<b>Incidents</b>\nNo active threads.\n"
                "Use /incident_thread &lt;id&gt; when alerted.",
                parse_mode="HTML",
            )
            return
        lines = ["<b>🚨 Active incidents</b>"]
        for t in sorted(threads, key=lambda x: x.created_at, reverse=True)[:8]:
            lines.append(
                f"• <code>{t.thread_id}</code> [{t.severity.value}] "
                f"{escape_node(t.title[:40])}"
            )
        lines.append("\n/incident_thread &lt;id&gt; · /inspect_replay &lt;news_id&gt;")
        await _answer_long(message, "\n".join(lines))

    @router.message(Command("incident_thread"))
    @admin_only("/incident_thread")
    async def cmd_incident_thread(message: Message) -> None:
        from bot.operator_console.context import get_operator_console

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /incident_thread <thread_id>")
            return
        console = get_operator_console()
        if console is None:
            await message.answer("Operator console unavailable.")
            return
        thread_id = parts[1].strip()
        if not thread_id.startswith("inc_"):
            thread_id = f"inc_{thread_id}"
        thread = console.hub.incidents.get(thread_id)
        if thread is None:
            await message.answer(f"No thread <code>{thread_id}</code>", parse_mode="HTML")
            return
        await _answer_long(message, thread.timeline_text())

    @router.message(Command("inspect_replay"))
    @admin_only("/inspect_replay")
    async def cmd_inspect_replay(message: Message) -> None:
        news_id = _parse_id(message, "/inspect_replay")
        if news_id is None:
            await message.answer("Usage: /inspect_replay <news_id>")
            return
        await _answer_long(
            message,
            story_lineage(editorial=editorial, news_id=news_id, node_id=node_id)
            + f"\n\nBundle: <code>evt_{news_id}</code> · /explain_story {news_id}",
        )

    @router.message(Command("inspect_lineage"))
    @admin_only("/inspect_lineage")
    async def cmd_inspect_lineage(message: Message) -> None:
        news_id = _parse_id(message, "/inspect_lineage")
        if news_id is None:
            await message.answer("Usage: /inspect_lineage <news_id>")
            return
        await _answer_long(
            message,
            story_lineage(editorial=editorial, news_id=news_id, node_id=node_id),
        )

    @router.message(Command("incident_timeline"))
    @admin_only("/incident_timeline")
    async def cmd_incident_timeline(message: Message) -> None:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /incident_timeline <thread_id>")
            return
        from bot.operator_console.context import get_operator_console

        console = get_operator_console()
        if console is None:
            await message.answer("Operator console unavailable.")
            return
        thread_id = parts[1].strip()
        if not thread_id.startswith("inc_"):
            thread_id = f"inc_{thread_id}"
        thread = console.hub.incidents.get(thread_id)
        if thread is None:
            await message.answer(f"No thread <code>{thread_id}</code>", parse_mode="HTML")
            return
        await _answer_long(message, thread.timeline_text())

    @router.message(Command("ops_usability"))
    @admin_only("/ops_usability")
    async def cmd_ops_usability(message: Message) -> None:
        from bot.operator_console.context import get_operator_console

        console = get_operator_console()
        if console is None:
            await message.answer("Operator console unavailable.")
            return
        fatigue = console.hub.fatigue.snapshot()
        await _answer_long(message, console.hub.usability.report(fatigue))

    @router.message(Command("why_flagged"))
    @admin_only("/why_flagged")
    async def cmd_why_flagged(message: Message) -> None:
        news_id = _parse_id(message, "/why_flagged")
        if news_id is None:
            await message.answer("Usage: /why_flagged <id>")
            return
        item = editorial.get_by_id(news_id)
        if item is None:
            await message.answer("Story not found.")
            return
        await _answer_long(message, why_flagged(item=item))

    @router.callback_query(F.data.startswith("op:"))
    async def on_operator_callback(query: CallbackQuery) -> None:
        if query.data is None or query.from_user is None:
            return
        parts = query.data.split(":")
        if len(parts) < 3:
            await query.answer("Invalid action")
            return
        if parts[1] == "batch" and len(parts) >= 4:
            await _handle_batch_callback(
                query,
                action=parts[2],
                ids_csv=parts[3],
                editorial=editorial,
                publisher=publisher,
                link_dedup=link_dedup,
                sources=sources,
                entities=entities,
                analytics=analytics,
                channel_router=channel_router,
                localizations=localizations,
                adaptive=adaptive,
                publish_idempotency=publish_idempotency,
                node_id=node_id,
                clusters=clusters,
                epistemic_layer=epistemic_layer,
            )
            return
        action, news_id_s = parts[1], parts[2]
        try:
            news_id = int(news_id_s)
        except ValueError:
            await query.answer("Invalid id")
            return
        console = get_operator_console()
        if console:
            console.hub.fatigue.record_operator_action()
            console.hub.usability.record_operator_action(action)
        if action == "explain":
            text = explain_story(
                editorial=editorial,
                clusters=clusters,
                epistemic=epistemic_layer,
                news_id=news_id,
            )
            await query.message.answer(text[:3900], parse_mode="HTML")
            await query.answer()
            return
        if action == "contradictions":
            if epistemic_layer is None:
                await query.answer("Epistemic unavailable")
                return
            text = epistemic_layer.calibration.explore_contradictions()
            await query.message.answer(text[:3900])
            await query.answer()
            return
        if action == "escalate":
            if console:
                await console.notify_incident(
                    kind="escalation",
                    title=f"Escalation #{news_id}",
                    severity="warn",
                    detail=f"Operator {query.from_user.id} escalated story",
                    replay_ref=f"evt_{news_id}",
                    suggested_action="Senior review required",
                )
            await query.answer("Escalated")
            return
        if action == "reject":
            editorial.reject_news(news_id)
            await query.answer("Rejected")
            await query.message.edit_reply_markup(reply_markup=None)
            return
        if action == "approve":
            item = editorial.approve_news(news_id)
            if item is None:
                await query.answer("Not pending")
                return
            flow = await publish_pending_item(
                item,
                publisher=publisher,
                editorial=editorial,
                link_dedup=link_dedup,
                sources=sources,
                entities=entities,
                analytics=analytics,
                channel_router=channel_router,
                localizations=localizations,
                adaptive=adaptive,
                idempotency=publish_idempotency,
                node_id=node_id,
                operator_approved=True,
                publish_guard=get_publish_guard(),
            )
            await query.message.edit_reply_markup(reply_markup=None)
            if flow.success:
                await query.answer("Published")
            else:
                await query.answer(f"Failed: {flow.error}", show_alert=True)
            return
        await query.answer("Unknown action")


def _parse_id(message: Message, command: str) -> int | None:
    parts = (message.text or "").split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def escape_node(node_id: str) -> str:
    from bot.operator_console.formatting import escape

    return escape(node_id)


async def _handle_batch_callback(
    query: CallbackQuery,
    *,
    action: str,
    ids_csv: str,
    editorial: EditorialRepository,
    publisher: ChannelPublisher,
    link_dedup: object | None,
    sources: object | None,
    entities: object | None,
    analytics: object | None,
    channel_router: ChannelRouter | None,
    localizations: object | None,
    adaptive: object | None,
    publish_idempotency: object | None,
    node_id: str,
    clusters: ClusterRepository,
    epistemic_layer: EpistemicIntegrityLayer | None,
) -> None:
    from bot.operator_console.context import get_operator_console

    console = get_operator_console()
    if console:
        console.hub.fatigue.record_operator_action()
        console.hub.usability.record_operator_action(f"batch:{action}")
    ids = [int(x) for x in ids_csv.split(",") if x.strip().isdigit()]
    if not ids:
        await query.answer("No ids")
        return
    if action == "explain":
        if query.message is None:
            await query.answer()
            return
        for news_id in ids[:3]:
            text = explain_story(
                editorial=editorial,
                clusters=clusters,
                epistemic=epistemic_layer,
                news_id=news_id,
            )
            await query.message.answer(text[:3900], parse_mode="HTML")
        await query.answer("Explained batch")
        return
    if action == "reject":
        for news_id in ids:
            editorial.reject_news(news_id)
        await query.answer(f"Rejected {len(ids)}")
        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)
        return
    if action == "approve":
        ok = 0
        for news_id in ids:
            item = editorial.approve_news(news_id)
            if item is None:
                continue
            flow = await publish_pending_item(
                item,
                publisher=publisher,
                editorial=editorial,
                link_dedup=link_dedup,
                sources=sources,
                entities=entities,
                analytics=analytics,
                channel_router=channel_router,
                localizations=localizations,
                adaptive=adaptive,
                idempotency=publish_idempotency,
                node_id=node_id,
                operator_approved=True,
                publish_guard=get_publish_guard(),
            )
            if flow.success:
                ok += 1
        await query.answer(f"Published {ok}/{len(ids)}")
        if query.message:
            await query.message.edit_reply_markup(reply_markup=None)
        return
    if action == "escalate" and console:
        await console.notify_incident(
            kind="escalation",
            title=f"Batch escalation ({len(ids)} stories)",
            severity="warn",
            detail=f"Operator escalated ids: {ids_csv[:120]}",
            suggested_action="Senior review required",
        )
        await query.answer("Escalated batch")
        return
    await query.answer("Unknown batch action")
