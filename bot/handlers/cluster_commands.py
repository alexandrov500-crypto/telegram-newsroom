from __future__ import annotations

from typing import TYPE_CHECKING

from aiogram.filters import Command
from aiogram.types import Message

from bot.distributed.types import NodeStatus
from bot.handlers import admin_only, router

if TYPE_CHECKING:
    from bot.distributed.cluster.coordinator import ClusterCoordinator
    from bot.storage.coordination_repository import CoordinationRepository


def register_cluster_handlers(
    *,
    coordinator: ClusterCoordinator | None,
    coordination: CoordinationRepository | None,
    cluster_scheduler: object | None,
    node_id: str,
    autonomous_runtime: object | None = None,
) -> None:
    @router.message(Command("cluster"))
    @admin_only("/cluster")
    async def cmd_cluster(message: Message) -> None:
        if coordinator is None:
            await message.answer("Cluster coordination disabled.")
            return
        leader = coordinator.current_leader()
        lines = [
            "Cluster status",
            f"  this_node: {node_id}",
            f"  leader: {leader or '(none)'}",
            f"  is_leader: {coordinator.is_leader}",
            f"  leader_changes: {coordinator.leader_changes}",
        ]
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("nodes"))
    @admin_only("/nodes")
    async def cmd_nodes(message: Message) -> None:
        if coordination is None:
            await message.answer("Cluster unavailable.")
            return
        nodes = coordination.list_nodes(include_stale=True)
        if not nodes:
            await message.answer("No cluster nodes registered.")
            return
        lines = ["Cluster nodes:", ""]
        for node in nodes[:25]:
            lines.append(
                f"- {node.node_id} role={node.role} region={node.region} "
                f"status={node.status} hb={node.last_heartbeat_at[-19:]}"
            )
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("leader"))
    @admin_only("/leader")
    async def cmd_leader(message: Message) -> None:
        if coordination is None:
            await message.answer("Cluster unavailable.")
            return
        leader = coordination.current_leader()
        await message.answer(f"Current leader: {leader or '(none)'}")

    @router.message(Command("failover"))
    @admin_only("/failover")
    async def cmd_failover(message: Message) -> None:
        if coordinator is None:
            await message.answer("Cluster unavailable.")
            return
        new_leader = coordinator.failover_leader()
        try:
            from bot.observability.metrics import record_node_failover

            record_node_failover()
        except Exception:
            pass
        await message.answer(f"Failover attempted. Leader: {new_leader or '(unchanged)'}")

    @router.message(Command("partitions"))
    @admin_only("/partitions")
    async def cmd_partitions(message: Message) -> None:
        if coordination is None:
            await message.answer("Cluster unavailable.")
            return
        parts = coordination.list_partitions()
        if not parts:
            await message.answer("No partitions assigned yet.")
            return
        lines = ["Partitions:", ""]
        for row in parts:
            lines.append(
                f"- {row['partition_key']}: node={row.get('assigned_node_id')} "
                f"paused={row.get('paused')} lag={row.get('lag_events')}"
            )
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("drain"))
    @admin_only("/drain")
    async def cmd_drain(message: Message) -> None:
        if coordinator is None or coordination is None:
            await message.answer("Cluster unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        target = parts[1].strip() if len(parts) > 1 else node_id
        if target == node_id:
            coordinator.drain()
            await message.answer(f"Draining this node ({node_id}).")
            return
        for node in coordination.list_nodes(include_stale=True):
            if node.node_id == target:
                coordination.set_node_status(
                    node_id=target,
                    role=node.role,
                    status=NodeStatus.DRAINING.value,
                )
                await message.answer(f"Node {target} marked draining.")
                return
        await message.answer(f"Node not found: {target}")

    @router.message(Command("rebalance"))
    @admin_only("/rebalance")
    async def cmd_rebalance(message: Message) -> None:
        if coordinator is None:
            await message.answer("Cluster unavailable.")
            return
        count = coordinator.rebalance_partitions()
        await message.answer(f"Rebalanced {count} partition(s).")

    @router.message(Command("degradation"))
    @admin_only("/degradation")
    async def cmd_degradation(message: Message) -> None:
        if autonomous_runtime is None:
            await message.answer("Autonomous runtime unavailable.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            mode = parts[1].strip().lower()
            snap = autonomous_runtime.degradation.operator_set(mode)
            await message.answer(f"Degradation set to {snap.mode} ({snap.reason})")
            return
        snap = autonomous_runtime.degradation.current()
        await message.answer(
            f"Mode: {snap.mode}\nPrevious: {snap.previous_mode}\n"
            f"Reason: {snap.reason}\nOverride: {snap.operator_override}",
        )

    @router.message(Command("topology"))
    @admin_only("/topology")
    async def cmd_topology(message: Message) -> None:
        if autonomous_runtime is None or coordination is None:
            await message.answer("Topology unavailable.")
            return
        snap = autonomous_runtime.topology.build_snapshot(coordination=coordination)
        lines = [
            f"Health: {snap.health_score:.2f}",
            f"Nodes: {len(snap.nodes)} unhealthy: {len(snap.unhealthy_nodes)}",
            "",
        ]
        for rec in snap.recommendations[:8]:
            lines.append(f"- {rec}")
        await message.answer("\n".join(lines)[:3900])

    @router.message(Command("policy_audit"))
    @admin_only("/policy_audit")
    async def cmd_policy_audit(message: Message) -> None:
        if autonomous_runtime is None:
            await message.answer("Policy runtime unavailable.")
            return
        audits = autonomous_runtime.policy._repo.recent_audits(limit=10)
        if not audits:
            await message.answer("No policy audits yet.")
            return
        lines = ["Recent policy decisions:", ""]
        for row in audits:
            lines.append(
                f"- {row['created_at'][-19:]} {row['decision']} "
                f"{row['action']}: {row['reason'][:60]}",
            )
        await message.answer("\n".join(lines)[:3900])
