"""Rule-based cluster digest when OpenAI is unavailable (debug / degraded paths only)."""

from __future__ import annotations

import time

from ai.cluster_summarizer import SummarizeClusterResult
from ai.execution_metadata import AIExecutionMetadata
from db.models import RawPost


def _normalize_raw(text: str) -> str:
    from app.editorial.wire_source_normalize import normalize_wire_source_text

    return normalize_wire_source_text(text)


def _shape_wire_fallback(body: str, *, headline: str = "", max_body_chars: int = 2800) -> str:
    from app.editorial.cb_brief_format import apply_cb_brief_shape, compose_cb_brief_text
    from app.publisher.draft_builder import finalize_draft_content

    body = _normalize_raw(body)
    if not body:
        return ""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    h = headline.strip()
    rest = "\n\n".join(lines[1:]) if len(lines) > 1 else body
    if not h and lines:
        h = lines[0]
    h, rest = apply_cb_brief_shape(h, rest)
    shaped = f"{h}\n\n{rest}".strip() if h and rest else compose_cb_brief_text(body, max_chars=max_body_chars)
    return finalize_draft_content(shaped, max_chars=max_body_chars)


def fallback_summarize_cluster(posts: list[RawPost], *, max_body_chars: int = 2800) -> SummarizeClusterResult:
    """Deterministic digest from raw post text — wire-shaped, no Telegram markdown."""
    from app.publisher.draft_builder import (
        complete_story_text,
        polish_channel_post,
        strip_telegram_markdown,
    )

    used: list[int] = []
    if not posts:
        body = "News digest (automated fallback summary)."
        exec_meta = _exec_meta()
        return SummarizeClusterResult(post_text=body, used_ids=[], headline="News update", execution=exec_meta)

    for p in posts[:12]:
        if p.id is not None:
            used.append(int(p.id))

    if len(posts) == 1:
        p = posts[0]
        raw = strip_telegram_markdown(str(p.text or ""))
        raw = _normalize_raw(raw)
        chunk = complete_story_text(raw, max_chars=max_body_chars)
        body = _shape_wire_fallback(chunk, max_body_chars=max_body_chars)
        headline = _headline_from_body(body)
        return SummarizeClusterResult(
            post_text=body,
            used_ids=used or ([int(posts[0].id)] if posts[0].id else []),
            headline=headline,
            execution=_exec_meta(),
        )

    paragraphs: list[str] = []
    for p in posts[:4]:
        raw = strip_telegram_markdown(str(p.text or ""))
        raw = _normalize_raw(raw)
        if not raw:
            continue
        chunk = complete_story_text(raw, max_chars=max(400, max_body_chars // max(1, min(len(posts), 4))))
        if chunk:
            paragraphs.append(chunk)
    body = polish_channel_post("\n\n".join(paragraphs), max_chars=max_body_chars)
    if not body or body == "News update.":
        body = polish_channel_post(
            _normalize_raw(strip_telegram_markdown(posts[0].text or "")),
            max_chars=max_body_chars,
        )
    body = _shape_wire_fallback(body, max_body_chars=max_body_chars)
    headline = _headline_from_body(body)
    if not used:
        used = [int(p.id) for p in posts if p.id is not None][:8]
    return SummarizeClusterResult(post_text=body, used_ids=used, headline=headline, execution=_exec_meta())


def _headline_from_body(body: str) -> str:
    for line in (body or "").splitlines():
        s = line.strip().lstrip("•").strip()
        if s.startswith("📌"):
            continue
        if len(s) >= 20:
            return s[:180]
    return "News update"


def _exec_meta() -> AIExecutionMetadata:
    return AIExecutionMetadata(
        prompt_id="rule_fallback",
        prompt_version="3",
        prompt_fingerprint="rule_fallback_v3_wire",
        model="rule_fallback",
        latency_sec=0.0,
        retry_count=0,
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
        estimated_cost_usd=None,
        completed_at_unix=time.time(),
        safety_warnings=("fallback_summarizer",),
    )
