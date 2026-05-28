"""Deterministic pipeline tick terminal state — every tick ends in draft or reject."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scheduler.runtime_context import PipelineContext

TERMINAL_STATES = frozenset({"committed_draft", "committed_reject", "committed_idle"})


@dataclass(frozen=True)
class TerminalStateResolution:
    terminal_state: str
    tick_status: str
    reason: str
    drafts_created: int

    def to_detail(self, ctx: PipelineContext) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "terminal_state": self.terminal_state,
            "terminal_reason": self.reason[:500],
            "summarize_idle": ctx.tick_summarize_idle_reason or "",
            "publish_outcome": ctx.tick_publish_outcome,
            "draft_id": ctx.tick_draft_id,
            "collect_rows": int(ctx.tick_collect_rows or 0),
            "cluster_size": int(ctx.last_cluster_size or 0),
        }
        media = getattr(ctx, "tick_media_detail", None)
        if isinstance(media, dict) and media:
            detail.update(media)
        return detail


def _idle_reason(ctx: PipelineContext) -> str:
    return (ctx.tick_summarize_idle_reason or "").strip()


def resolve_terminal_state(
    ctx: PipelineContext,
    *,
    raw_unprocessed: int = 0,
) -> TerminalStateResolution:
    """
    Map tick context to exactly one terminal outcome.

    - committed_draft: draft_id persisted this tick
    - committed_reject: explicit editorial/AI/pipeline reject (logged idle reason)
    - committed_idle: no backlog work (not a failure)
    """
    if ctx.tick_draft_id is not None:
        return TerminalStateResolution(
            terminal_state="committed_draft",
            tick_status="ok",
            reason=f"draft_id={ctx.tick_draft_id}",
            drafts_created=1,
        )

    idle = _idle_reason(ctx)
    if idle.startswith("no_unprocessed") or (raw_unprocessed <= 0 and not idle):
        return TerminalStateResolution(
            terminal_state="committed_idle",
            tick_status="ok",
            reason=idle or "no_unprocessed_posts",
            drafts_created=0,
        )

    if idle:
        return TerminalStateResolution(
            terminal_state="committed_reject",
            tick_status="reject",
            reason=idle,
            drafts_created=0,
        )

    if raw_unprocessed > 0:
        return TerminalStateResolution(
            terminal_state="committed_reject",
            tick_status="reject",
            reason="pipeline_unresolved:backlog_without_terminal",
            drafts_created=0,
        )

    return TerminalStateResolution(
        terminal_state="committed_idle",
        tick_status="ok",
        reason="no_backlog",
        drafts_created=0,
    )


def apply_forced_reject_idle(ctx: PipelineContext, reason: str) -> None:
    """Set summarize idle reason when summarize path exits without draft."""
    clean = (reason or "pipeline_reject").strip()[:240]
    if not clean.startswith(
        (
            "desk_reject:",
            "openai_failed:",
            "load_shedding:",
            "ai_budget:",
            "cluster_",
            "ai_summarization:",
        )
    ):
        clean = f"openai_failed:{clean}"
    ctx.tick_summarize_idle_reason = clean
