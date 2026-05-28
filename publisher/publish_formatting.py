from __future__ import annotations

import json
import re
from typing import Any

from utils.telegram_html import escape_telegram_html, sanitize_telegram_html_output


def _normalize_emoji_variants(text: str) -> str:
    """Light normalization: collapse repeated emoji spacing (deterministic)."""
    t = re.sub(r"[\u200d\uFE0F]+", "", text)
    t = re.sub(r" {2,}", " ", t)
    return t.strip()


def _normalize_bullets(text: str) -> str:
    lines = []
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s.startswith(("-", "*", "•")):
            s = "• " + s.lstrip("-*• ").strip()
        lines.append(s)
    return "\n".join(lines)


def _quote_block(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    parts = [f"<blockquote>{escape_telegram_html(p.strip())}</blockquote>" for p in t.split("\n\n") if p.strip()]
    return "\n".join(parts[:3])


def format_body_as_html(content: str) -> str:
    raw = _normalize_bullets(_normalize_emoji_variants(content or ""))
    if not raw:
        return "<i>(empty)</i>"
    blocks: list[str] = []
    for para in raw.split("\n\n"):
        p = para.strip()
        if not p:
            continue
        if p.startswith(">"):
            inner = "\n".join(line.lstrip(">").strip() for line in p.splitlines())
            blocks.append(_quote_block(inner))
        else:
            lines = p.splitlines()
            if all(l.strip().startswith("•") for l in lines if l.strip()):
                items = []
                for l in lines:
                    s = l.strip()
                    if not s:
                        continue
                    items.append(f"<b>•</b> {escape_telegram_html(s.lstrip('•').strip())}")
                blocks.append("\n".join(items))
            else:
                blocks.append(f"<b>{escape_telegram_html(lines[0])}</b>" if lines else "")
                if len(lines) > 1:
                    blocks.append(escape_telegram_html("\n".join(lines[1:])))
    out = "\n\n".join(b for b in blocks if b)
    if not out:
        return escape_telegram_html(raw[:8000])
    return sanitize_telegram_html_output(out)


def format_sources_footer_html(sources: str | list[dict[str, Any]] | None, *, max_items: int = 12) -> str:
    items: list[str] = []
    if isinstance(sources, list):
        data = sources[:max_items]
    else:
        try:
            data = json.loads(sources or "[]")
        except (json.JSONDecodeError, TypeError):
            return f"<i>Sources:</i> {escape_telegram_html(str(sources)[:400])}"
        if not isinstance(data, list):
            return f"<i>Sources:</i> {escape_telegram_html(str(data)[:400])}"
        data = data[:max_items]
    for it in data:
        if not isinstance(it, dict):
            continue
        ch = str(it.get("channel", "?"))
        mid = it.get("message_id", "?")
        items.append(f"• {escape_telegram_html(ch)} ({escape_telegram_html(str(mid))})")
    if not items:
        return "<i>Sources:</i> —"
    return "<b>Sources</b>\n" + "\n".join(items)


def build_channel_message_html(
    content: str,
    sources: str | list[dict[str, Any]] | None,
    *,
    draft_id: int,
    max_total_chars: int = 12000,
    include_sources: bool = False,
    include_draft_id_footer: bool = False,
    runtime_dir: str | None = None,
) -> str:
    """
    Public channel HTML — delegates to ``public_renderer`` (no debug metadata).

    Legacy flags ``include_sources`` / ``include_draft_id_footer`` are ignored for channel
    safety; use ``render_internal_review_html`` in admin for diagnostics.
    """
    from app.editorial.public_post_formatter import format_public_post_html

    _ = include_sources, include_draft_id_footer
    if runtime_dir is None:
        import os

        runtime_dir = os.getenv("RUNTIME_STATE_DIR", "var/runtime").strip() or "var/runtime"
    return format_public_post_html(
        content,
        sources,
        draft_id=draft_id,
        max_total_chars=max_total_chars,
        runtime_dir=runtime_dir,
    )
