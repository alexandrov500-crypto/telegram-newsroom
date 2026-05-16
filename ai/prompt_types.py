"""Typed prompt references for lightweight AI governance (no template engine)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PromptSpec:
    """Stable identity for a logical prompt family + version + content fingerprint."""

    prompt_id: str
    prompt_version: str
    fingerprint: str
    models_recommended: tuple[str, ...] = ("gpt-4.1-mini", "gpt-4o-mini")
    metadata: dict[str, Any] | None = None
