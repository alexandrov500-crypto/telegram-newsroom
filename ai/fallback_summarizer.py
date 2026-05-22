"""Rule-based cluster digest when OpenAI is unavailable (debug / degraded paths only)."""

from __future__ import annotations

import time

from ai.cluster_summarizer import SummarizeClusterResult
from ai.execution_metadata import AIExecutionMetadata
from db.models import RawPost


def fallback_summarize_cluster(posts: list[RawPost], *, max_body_chars: int = 2800) -> SummarizeClusterResult:
    """Deterministic digest from raw post text — no network."""
    used: list[int] = []
    lines: list[str] = []
    for p in posts[:12]:
        if p.id is None:
            continue
        used.append(int(p.id))
        ch = str(p.channel_name or "").strip()
        snippet = (p.text or "").strip().replace("\n", " ")
        if len(snippet) > 400:
            snippet = snippet[:397] + "..."
        if snippet:
            lines.append(f"• [{ch}] {snippet}" if ch else f"• {snippet}")
    if not used:
        used = [int(p.id) for p in posts if p.id is not None][:8]
    body = "\n".join(lines).strip()
    if not body:
        body = "News digest (automated fallback summary)."
    if len(body) > max_body_chars:
        body = body[: max_body_chars - 3].rstrip() + "..."
    headline = (lines[0].lstrip("• ").split("]", 1)[-1].strip()[:180] if lines else "News update")
    exec_meta = AIExecutionMetadata(
        prompt_id="rule_fallback",
        prompt_version="1",
        prompt_fingerprint="rule_fallback_v1",
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
    return SummarizeClusterResult(post_text=body, used_ids=used, headline=headline, execution=exec_meta)
