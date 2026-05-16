"""Lightweight textual diff helpers for moderation (no external diff engine)."""

from __future__ import annotations

import difflib
import json
from typing import Any


def unified_text_diff(before: str, after: str, *, label_a: str = "before", label_b: str = "after", context: int = 3) -> str:
    a = (before or "").splitlines()
    b = (after or "").splitlines()
    return "\n".join(
        difflib.unified_diff(
            a,
            b,
            fromfile=label_a,
            tofile=label_b,
            lineterm="",
            n=max(1, min(context, 10)),
        )
    )


def headline_and_lead_diff(*, draft_content: str, editor_title: str | None, editor_summary: str | None) -> dict[str, Any]:
    """Compare stored editor fields vs first lines of body (heuristic headline/lead)."""
    lines = (draft_content or "").splitlines()
    auto_head = (lines[0] if lines else "").strip()
    auto_lead = "\n".join(lines[1:6]).strip() if len(lines) > 1 else ""
    et = (editor_title or "").strip()
    es = (editor_summary or "").strip()
    return {
        "title_diff": unified_text_diff(auto_head, et, label_a="draft_first_line", label_b="editor_title") if et else "",
        "summary_diff": unified_text_diff(auto_lead, es, label_a="draft_early_lines", label_b="editor_summary") if es else "",
        "auto_headline": auto_head[:500],
        "editor_title": et[:500],
    }


def ai_vs_editor_body_diff(*, ai_text: str | None, current_content: str) -> str:
    """``ai_text`` may come from draft_extras quality or a stored snapshot if present."""
    return unified_text_diff(ai_text or "", current_content or "", label_a="ai_snapshot", label_b="current_content")


def format_edit_history(edit_history_json: str | None, *, max_entries: int = 40) -> str:
    """Human-readable lines from ``Draft.edit_history`` JSON list."""
    raw = edit_history_json or "[]"
    try:
        arr = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(arr, list):
        return ""
    tail = arr[-max(1, min(max_entries, 120)) :]
    lines: list[str] = []
    for ent in tail:
        if not isinstance(ent, dict):
            continue
        ts = str(ent.get("ts") or "")
        act = str(ent.get("action") or "")
        extra = {k: v for k, v in ent.items() if k not in ("ts", "action")}
        lines.append(f"{ts}  {act}  {json.dumps(extra, ensure_ascii=False, default=str)}")
    return "\n".join(lines)
