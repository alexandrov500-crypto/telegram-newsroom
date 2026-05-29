from __future__ import annotations

import os

from openai import AsyncOpenAI


def create_openai_client(
    api_key: str,
    *,
    timeout: float = 120.0,
    max_retries: int = 2,
) -> AsyncOpenAI:
    # Optional relay/proxy endpoint so deployments in regions where the OpenAI
    # API is geo-blocked (e.g. some VPS hosts) can reach it through an allowed
    # region. Point OPENAI_BASE_URL at a compatible relay to restore live AI
    # summarization; when unset, the official endpoint is used.
    base_url = os.getenv("OPENAI_BASE_URL", "").strip()
    kwargs: dict[str, object] = {
        "api_key": api_key,
        "timeout": timeout,
        "max_retries": max_retries,
    }
    if base_url:
        kwargs["base_url"] = base_url
    return AsyncOpenAI(**kwargs)
