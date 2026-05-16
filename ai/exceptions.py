from __future__ import annotations


class SummarizerError(RuntimeError):
    """Raised when cluster summarization fails after retries (OpenAI / parsing)."""

