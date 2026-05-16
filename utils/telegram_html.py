from __future__ import annotations

import html
import re


def escape_telegram_html(text: str) -> str:
    """
    Escape dynamic text for Telegram HTML parse mode.
    Avoids unsupported tags by escaping all angle brackets.
    """
    return html.escape(text, quote=False)


def strip_html_tags(text: str) -> str:
    """Remove simple HTML-like tags for plain-text fallbacks."""
    return re.sub(r"<[^>]+>", "", text)


def sanitize_telegram_html_output(html: str) -> str:
    """
    If suspicious active-content patterns appear, fall back to escaped plain text.
    """
    if not html:
        return ""
    if re.search(r"(?i)<\s*script|javascript\s*:|data:text/html|\bon\w+\s*=", html):
        return escape_telegram_html(strip_html_tags(html))
    return html
