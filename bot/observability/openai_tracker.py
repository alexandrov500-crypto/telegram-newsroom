from __future__ import annotations

import time
from dataclasses import dataclass

from bot.observability.metrics import record_openai_usage
from bot.storage.observability_repository import ObservabilityRepository


@dataclass(frozen=True)
class OpenAITracker:
    """Bridge Prometheus metrics and SQLite usage persistence."""

    repo: ObservabilityRepository | None
    cost_per_1k_input: float = 0.00015
    cost_per_1k_output: float = 0.0006

    def estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens / 1000.0) * self.cost_per_1k_input + (
            completion_tokens / 1000.0
        ) * self.cost_per_1k_output

    def record(
        self,
        *,
        operation: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        success: bool,
        latency_ms: int = 0,
        pending_news_id: int | None = None,
    ) -> None:
        cost = self.estimate_cost(prompt_tokens, completion_tokens)
        record_openai_usage(
            operation=operation,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            success=success,
            cost_usd=cost,
        )
        if self.repo is not None:
            self.repo.record_openai_event(
                operation=operation,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
                success=success,
                pending_news_id=pending_news_id,
            )


def timed_openai_call() -> tuple[int, int]:
    """Return (latency_ms, monotonic_start_ms) helper — caller records after await."""
    started = time.perf_counter()
    return 0, int(started * 1000)
