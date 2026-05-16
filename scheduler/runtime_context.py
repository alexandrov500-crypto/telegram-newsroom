from __future__ import annotations

from dataclasses import dataclass, field

from aiogram import Bot
from openai import AsyncOpenAI

from app.config import Settings


@dataclass(slots=True)
class PipelineContext:
    settings: Settings
    bot: Bot
    openai: AsyncOpenAI
    tick_timings: dict[str, float] = field(default_factory=dict)
    last_scheduler_wall_sec: float = 0.0
    tick_in_progress: bool = False
    last_cluster_size: int = 0
    duplicate_skipped_this_tick: bool = False


_ACTIVE: PipelineContext | None = None


def get_pipeline_context() -> PipelineContext | None:
    return _ACTIVE


def set_pipeline_context(ctx: PipelineContext | None) -> None:
    global _ACTIVE
    _ACTIVE = ctx
