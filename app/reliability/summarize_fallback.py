"""Unified OpenAI / rule-fallback path for cluster summarization (one handler)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ai.fallback_summarizer import fallback_summarize_cluster
from utils.structured_log import log_event

if TYPE_CHECKING:
    from ai.summarizer import SummarizedCluster
    from scheduler.runtime_context import PipelineContext

logger = logging.getLogger(__name__)


@dataclass
class SummarizePathResult:
    summary: SummarizedCluster | None
    ai_status: str
    rejected: bool


def _starvation_fallback_active() -> bool:
    try:
        from app.editorial.desk_starvation import desk_threshold_context

        return bool(desk_threshold_context().publish_starvation_detected)
    except Exception:
        return False


def _rule_fallback_when_ai_down() -> bool:
    """Reliability flag: keep producing drafts via the rule-based summarizer
    whenever OpenAI is unavailable, so the channel never runs dry on fresh
    content (algorithm/provider outages can't stall the publishing pipeline).
    Default on; set SUMMARIZE_RULE_FALLBACK_WHEN_AI_DOWN=false to require OpenAI.
    """
    import os

    return os.getenv("SUMMARIZE_RULE_FALLBACK_WHEN_AI_DOWN", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def fallback_allowed(*, bypass: bool, minimal_mode: bool, cluster: list[Any] | None = None, settings: Any | None = None) -> bool:
    if cluster and settings is not None:
        from app.editorial.source_languages import (
            cluster_source_language,
            publish_output_language,
            requires_translation,
        )

        src = cluster_source_language(cluster, settings)
        out = publish_output_language(settings)
        if requires_translation(src, out):
            return False
    if bypass or minimal_mode:
        return True
    if _starvation_fallback_active():
        return True
    if _rule_fallback_when_ai_down():
        return True
    try:
        from app.editorial.burnin_governance import burnin_openai_always_fallback

        return burnin_openai_always_fallback()
    except Exception:
        return False


def rule_fallback_summary(cluster: list[Any], settings: Any, *, recovery: str) -> SummarizedCluster:
    from app.runtime_activity import record_fallback_success

    sc = fallback_summarize_cluster(cluster, max_body_chars=settings.max_post_chars)
    record_fallback_success()
    log_event(logger, "openai.summarize_fallback", recovery=recovery)
    return sc


async def summarize_openai_or_fallback(
    ctx: PipelineContext,
    *,
    cluster: list[Any],
    openai: Any,
    settings: Any,
    ai_gate_open: bool,
    bypass: bool,
    minimal_mode: bool,
) -> SummarizePathResult:
    """
    Single summarization path: primary OpenAI when gate open, else rule fallback.
    On SummarizerError: fallback if allowed, else committed_reject via idle reason.
    """
    from app.observability.execution_graph_trace import record_summarize_path

    record_summarize_path(ai_status="enter")
    t_ai0 = time.perf_counter()
    from ai.summarizer import SummarizerError, summarize_cluster
    from app.reliability.terminal_state_resolver import apply_forced_reject_idle
    from app.runtime_activity import record_fallback_success
    from app.openai_circuit import get_openai_circuit

    if not ai_gate_open:
        from app.editorial.source_languages import (
            cluster_source_language,
            publish_output_language,
            requires_translation,
        )

        src = cluster_source_language(cluster, settings)
        out = publish_output_language(settings)
        if requires_translation(src, out):
            from app.editorial.translate_fallback import translate_cluster_posts

            translated = await translate_cluster_posts(cluster, settings)
            if translated:
                sc = rule_fallback_summary(translated, settings, recovery="zh_translate_fallback")
                record_summarize_path(ai_status="zh_translate_fallback")
                return SummarizePathResult(summary=sc, ai_status="zh_translate_fallback", rejected=False)
            if not fallback_allowed(bypass=bypass, minimal_mode=minimal_mode, cluster=cluster, settings=settings):
                reason = f"translation_required_no_openai:{src}->{out}"
                apply_forced_reject_idle(ctx, reason)
                record_summarize_path(ai_status="translation_required")
                return SummarizePathResult(summary=None, ai_status="translation_required", rejected=True)
        elif not fallback_allowed(bypass=bypass, minimal_mode=minimal_mode, cluster=cluster, settings=settings):
            reason = f"fallback_blocked_ai_gate_closed:{src}->{out}"
            apply_forced_reject_idle(ctx, reason)
            record_summarize_path(ai_status="fallback_blocked")
            return SummarizePathResult(summary=None, ai_status="fallback_blocked", rejected=True)
        sc = rule_fallback_summary(cluster, settings, recovery="ai_gate_closed")
        record_summarize_path(ai_status="skipped_fallback")
        return SummarizePathResult(summary=sc, ai_status="skipped_fallback", rejected=False)

    try:
        sc = await summarize_cluster(
            openai,
            settings=settings,
            model=settings.openai_model,
            posts=cluster,
            max_json_retries=settings.openai_json_max_retries,
            request_timeout_sec=settings.openai_request_timeout_sec,
            log_chat_latency=True,
        )
        from app.observability.runtime_health import record_openai_latency_ms

        record_openai_latency_ms((time.perf_counter() - t_ai0) * 1000.0)
        record_summarize_path(ai_status="called")
        return SummarizePathResult(summary=sc, ai_status="called", rejected=False)
    except SummarizerError as exc:
        circuit = get_openai_circuit()
        circuit.record_failure(str(exc))
        try:
            from ops.incidents.triggers import note_openai_failure

            note_openai_failure(settings, reason=str(exc))
        except Exception:
            pass
        from app.editorial.source_languages import (
            cluster_source_language,
            publish_output_language,
            requires_translation,
        )

        src = cluster_source_language(cluster, settings)
        out = publish_output_language(settings)
        if requires_translation(src, out):
            from app.editorial.translate_fallback import translate_cluster_posts

            translated = await translate_cluster_posts(cluster, settings)
            if translated:
                sc = rule_fallback_summary(translated, settings, recovery="zh_translate_fallback")
                log_event(logger, "openai.summarize_failed", error=str(exc), recovery="zh_translate_fallback")
                record_summarize_path(ai_status="failed_zh_translate_fallback")
                return SummarizePathResult(summary=sc, ai_status="failed_zh_translate_fallback", rejected=False)
        starvation = _starvation_fallback_active()
        if fallback_allowed(bypass=bypass, minimal_mode=minimal_mode, cluster=cluster, settings=settings) or starvation:
            recovery = "rule_fallback_starvation" if starvation else "rule_fallback"
            sc = rule_fallback_summary(cluster, settings, recovery=recovery)
            status = "failed_fallback_starvation" if starvation else "failed_fallback"
            log_event(logger, "openai.summarize_failed", error=str(exc), recovery=recovery)
            record_summarize_path(ai_status=status)
            return SummarizePathResult(summary=sc, ai_status=status, rejected=False)
        err_short = str(exc).split("\n", 1)[0][:200]
        apply_forced_reject_idle(ctx, f"openai_failed:{err_short}")
        log_event(logger, "openai.summarize_failed", error=str(exc), recovery="committed_reject")
        record_summarize_path(ai_status="failed")
        return SummarizePathResult(summary=None, ai_status="failed", rejected=True)

    if sc is None:
        if bypass or fallback_allowed(bypass=False, minimal_mode=minimal_mode, cluster=cluster, settings=settings):
            sc = rule_fallback_summary(cluster, settings, recovery="empty_model_fallback")
            return SummarizePathResult(summary=sc, ai_status="skipped_fallback", rejected=False)
        apply_forced_reject_idle(ctx, "ai_summarization:no_summarizer_result")
        record_summarize_path(ai_status="no_result")
        return SummarizePathResult(summary=None, ai_status="no_result", rejected=True)

    record_summarize_path(ai_status="called")
    return SummarizePathResult(summary=sc, ai_status="called", rejected=False)
