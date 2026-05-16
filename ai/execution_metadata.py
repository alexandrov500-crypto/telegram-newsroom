"""Structured accounting for OpenAI (and similar) calls from the newsroom pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AIExecutionMetadata:
    prompt_id: str
    prompt_version: str
    prompt_fingerprint: str
    model: str
    latency_sec: float
    retry_count: int
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    completed_at_unix: float
    safety_warnings: tuple[str, ...] = ()

    def to_draft_extras_patch(self) -> dict[str, Any]:
        return {
            "ai_generation": {
                "prompt_id": self.prompt_id,
                "prompt_version": self.prompt_version,
                "prompt_fingerprint": self.prompt_fingerprint,
                "model": self.model,
                "latency_sec": round(self.latency_sec, 4),
                "retry_count": int(self.retry_count),
                "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens,
                "total_tokens": self.total_tokens,
                "estimated_cost_usd": self.estimated_cost_usd,
                "completed_at_unix": self.completed_at_unix,
                "safety_warnings": list(self.safety_warnings),
            }
        }
