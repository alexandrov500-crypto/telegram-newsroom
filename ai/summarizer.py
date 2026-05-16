from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from ai.exceptions import SummarizerError

logger = logging.getLogger(__name__)

__all__ = [
    "BaseSummarizer",
    "FakeSummarizer",
    "OpenAISummarizer",
    "SummarizeClusterResult",
    "SummarizerError",
    "summarize_cluster",
]


class BaseSummarizer(ABC):
    """Sync abstraction for plain-text summarization (tests, editorial offline path)."""

    @abstractmethod
    def summarize(self, text: str) -> str:
        raise NotImplementedError


class FakeSummarizer(BaseSummarizer):
    """Deterministic, no network — for pytest and default editorial ``run_pipeline``."""

    def __init__(self, *, max_chars: int = 200) -> None:
        self._max_chars = max(1, min(max_chars, 10_000))

    def summarize(self, text: str) -> str:
        return (text or "").strip()[: self._max_chars].strip()


class OpenAISummarizer(BaseSummarizer):
    """
    Plain-text summarization via ``AsyncOpenAI`` (separate from JSON cluster draft).

    Uses ``asyncio.run`` — do not call ``summarize`` from inside a running event loop.
    """

    def __init__(
        self,
        client: Any,
        model: str,
        *,
        max_retries: int = 3,
        request_timeout_sec: float = 90.0,
        max_input_chars: int = 24_000,
    ) -> None:
        self._client = client
        self._model = model
        self._max_retries = max(1, min(max_retries, 8))
        self._request_timeout_sec = max(10.0, min(request_timeout_sec, 300.0))
        self._max_input_chars = max(1000, min(max_input_chars, 100_000))

    def summarize(self, text: str) -> str:
        import asyncio

        t = (text or "").strip()
        if not t:
            return ""
        if len(t) > self._max_input_chars:
            t = t[: self._max_input_chars].rstrip()

        async def _with_retries() -> str:
            import asyncio as aio

            from openai import APIStatusError

            from utils.metrics import inc
            from utils.structured_log import log_event

            last_err: str | None = None
            for attempt in range(1, self._max_retries + 1):
                try:
                    t0 = time.perf_counter()
                    out = await aio.wait_for(
                        self._client.chat.completions.create(
                            model=self._model,
                            temperature=0.2,
                            max_tokens=512,
                            messages=[
                                {
                                    "role": "system",
                                    "content": (
                                        "You are a news editor. Summarize the user's text in neutral tone, "
                                        "at most ~200 words. Output plain text only, no markdown fences."
                                    ),
                                },
                                {"role": "user", "content": t},
                            ],
                        ),
                        timeout=self._request_timeout_sec,
                    )
                    log_event(
                        logger,
                        "openai.text_summarize_duration_sec",
                        duration_sec=round(time.perf_counter() - t0, 4),
                        model=self._model,
                    )
                    choice = out.choices[0].message.content
                    return (choice or "").strip()
                except aio.TimeoutError:
                    log_event(logger, "openai.text_summarize_timeout", attempt=attempt, model=self._model)
                    last_err = "timeout"
                except APIStatusError as exc:
                    log_event(
                        logger,
                        "openai.text_summarize_api_error",
                        attempt=attempt,
                        model=self._model,
                        error=repr(exc)[:400],
                    )
                    last_err = repr(exc)
                except Exception as exc:
                    log_event(
                        logger,
                        "openai.text_summarize_failed",
                        attempt=attempt,
                        model=self._model,
                        error=repr(exc)[:400],
                    )
                    last_err = repr(exc)
                if attempt < self._max_retries:
                    inc("openai_retries")
            inc("openai_failures")
            raise SummarizerError(f"OpenAI text summarization failed after retries: {last_err}")

        try:
            return asyncio.run(_with_retries())
        except RuntimeError as exc:
            if "asyncio.run()" in str(exc) and "running event loop" in str(exc):
                raise SummarizerError(
                    "OpenAISummarizer.summarize cannot run inside an active asyncio loop; "
                    "use FakeSummarizer in async contexts or add an async API."
                ) from exc
            raise


async def summarize_cluster(*args: Any, **kwargs: Any) -> Any:
    """Lazy facade — loads cluster/OpenAI stack only when the scheduler calls it."""
    from ai.cluster_summarizer import summarize_cluster as _impl

    return await _impl(*args, **kwargs)


from ai.cluster_summarizer import SummarizeClusterResult  # noqa: E402
