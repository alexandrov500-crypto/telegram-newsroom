from __future__ import annotations

from openai import AsyncOpenAI


def create_openai_client(
    api_key: str,
    *,
    timeout: float = 120.0,
    max_retries: int = 2,
) -> AsyncOpenAI:
    return AsyncOpenAI(api_key=api_key, timeout=timeout, max_retries=max_retries)
