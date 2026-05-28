"""Editorial experiment flags (sandbox)."""

from __future__ import annotations

import os


def experiment_enabled(name: str) -> bool:
    key = f"EDITORIAL_EXPERIMENT_{name.strip().upper().replace('-', '_')}"
    return os.getenv(key, "").strip().lower() in {"1", "true", "yes", "on"}


def active_experiments() -> dict[str, bool]:
    prefix = "EDITORIAL_EXPERIMENT_"
    out: dict[str, bool] = {}
    for k, v in os.environ.items():
        if not k.startswith(prefix):
            continue
        name = k.removeprefix(prefix).lower()
        out[name] = v.strip().lower() in {"1", "true", "yes", "on"}
    return out


def sandbox_prompt_overrides() -> list[str]:
    """Extra prompt lines when experiments enabled."""
    lines: list[str] = []
    if experiment_enabled("humor_light"):
        lines.append("Experiment: one gentle humorous closing line max, never sarcastic.")
    if experiment_enabled("shorter_posts"):
        lines.append("Experiment: target 2 short paragraphs, under 600 characters if possible.")
    if experiment_enabled("no_closing_quip"):
        lines.append("Experiment: omit closing humor line entirely.")
    return lines
