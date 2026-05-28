"""Rule-based cluster digest when OpenAI is unavailable (debug / degraded paths only)."""

from __future__ import annotations

import time

from ai.cluster_summarizer import SummarizeClusterResult
from ai.execution_metadata import AIExecutionMetadata
from db.models import RawPost


def fallback_summarize_cluster(posts: list[RawPost], *, max_body_chars: int = 2800) -> SummarizeClusterResult:
    """Deterministic digest from raw post text — no network, plain text (no Telegram markdown)."""
    from app.publisher.draft_builder import (
        complete_story_text,
        format_single_source_draft,
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
        body = format_single_source_draft(
            {
                "text": p.text or "",
                "source": p.channel_name or "",
                "message_id": p.message_id,
            },
            max_chars=max_body_chars,
        )
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
        if not raw:
            continue
        chunk = complete_story_text(raw, max_chars=max(400, max_body_chars // max(1, min(len(posts), 4))))
        if chunk:
            paragraphs.append(chunk)
    body = polish_channel_post("\n\n".join(paragraphs), max_chars=max_body_chars)
    if not body or body == "News update.":
        body = polish_channel_post(
            strip_telegram_markdown(posts[0].text or ""),
            max_chars=max_body_chars,
        )
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
        prompt_version="2",
        prompt_fingerprint="rule_fallback_v2_plain",
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
