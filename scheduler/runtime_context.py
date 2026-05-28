from __future__ import annotations

from dataclasses import dataclass, field

from aiogram import Bot
from openai import AsyncOpenAI

from app.config import Settings
from app.state.pipeline_decision_engine import PipelineDecision
from app.state.pipeline_state_engine import PipelineExecutionDecision


@dataclass(slots=True)
class PipelineContext:
    settings: Settings
    bot: Bot
    openai: AsyncOpenAI
    ai_pipeline_enabled: bool = True  # DEPRECATED mirror — use pipeline_decision.should_execute
    collector_enabled: bool = True
    pipeline_decision: PipelineDecision | None = None
    pipeline_execution: PipelineExecutionDecision | None = None  # legacy adapter view
    pipeline_trace_id: str = ""
    tick_timings: dict[str, float] = field(default_factory=dict)
    last_scheduler_wall_sec: float = 0.0
    tick_in_progress: bool = False
    last_cluster_size: int = 0
    duplicate_skipped_this_tick: bool = False
    debug_trace_cluster_id: str | None = None
    tick_collect_rows: int = 0
    tick_summarize_idle_reason: str = ""
    tick_draft_id: int | None = None
    tick_publish_outcome: str = "not_reached"
    is_breaking_stream: bool = False
    tick_failures: int = 0
    tick_media_detail: dict[str, object] | None = None


_ACTIVE: PipelineContext | None = None


def get_pipeline_context() -> PipelineContext | None:
    return _ACTIVE


def set_pipeline_context(ctx: PipelineContext | None) -> None:
    global _ACTIVE
    _ACTIVE = ctx
