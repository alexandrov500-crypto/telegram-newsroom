"""Rough USD estimates for chat completions (heuristic; not billing truth)."""

from __future__ import annotations

# USD per 1M tokens (input, output) — conservative defaults for small models.
_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.0),
    "gpt-4-turbo": (10.0, 30.0),
}


def estimate_chat_cost_usd(*, model: str, input_tokens: int, output_tokens: int) -> float | None:
    m = (model or "").strip().lower()
    rates = None
    for key, tup in _PER_MILLION.items():
        if m.startswith(key):
            rates = tup
            break
    if rates is None:
        return None
    inp_rate, out_rate = rates
    return round((input_tokens / 1_000_000.0) * inp_rate + (output_tokens / 1_000_000.0) * out_rate, 8)
