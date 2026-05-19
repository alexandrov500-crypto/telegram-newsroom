from __future__ import annotations

import html
from datetime import datetime, timezone

TELEGRAM_MAX = 4096
SAFE_MAX = 3900


def escape(text: str) -> str:
    return html.escape(str(text), quote=False)


def now_utc_short() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%SZ")


def severity_marker(severity: str) -> str:
    return {
        "info": "ℹ️",
        "warn": "⚠️",
        "critical": "🚨",
        "ok": "✅",
    }.get(severity, "•")


def split_message(text: str, *, max_len: int = SAFE_MAX) -> list[str]:
    if len(text) <= max_len:
        return [text]
    parts: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            parts.append(remaining)
            break
        cut = remaining.rfind("\n", 0, max_len)
        if cut < max_len // 3:
            cut = max_len
        parts.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return parts


def format_header(tag: str, severity: str = "info") -> str:
    return f"{severity_marker(severity)} <b>[{escape(tag)}]</b>"


def clamp_lines(text: str, *, max_lines: int = 10) -> str:
    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text
    trimmed = lines[: max_lines - 1]
    trimmed.append(f"<i>+{len(lines) - max_lines + 1} more (truncated)</i>")
    return "\n".join(trimmed)


def alert_footer(
    *,
    replay_ref: str | None = None,
    route: str | None = None,
    contradictions: int | None = None,
    bundle: str | None = None,
) -> str:
    parts: list[str] = []
    if replay_ref:
        parts.append(f"replay <code>{escape(replay_ref)}</code>")
    if route:
        parts.append(f"route {escape(route)}")
    if contradictions is not None and contradictions > 0:
        parts.append(f"⚡{contradictions} contradictions")
    if bundle:
        parts.append(f"bundle <code>{escape(bundle)}</code>")
    return " · ".join(parts) if parts else ""
