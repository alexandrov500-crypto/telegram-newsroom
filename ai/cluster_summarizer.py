from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any

from openai import APIStatusError, AsyncOpenAI
from pydantic import ValidationError

from ai.cost_estimation import estimate_chat_cost_usd
from ai.editorial import build_system_prompt, build_user_prompt, digest_prompt_active
from ai.exceptions import SummarizerError
from ai.execution_metadata import AIExecutionMetadata
from ai.prompt_registry import resolve_cluster_draft_prompt
from ai.safety_hooks import scan_draft_output
from app.config import Settings
from app.schemas import OpenAIClusterResponse
from db.models import RawPost
from utils.metrics import inc, set_gauge
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_REFUSAL_RE = re.compile(
    r"(?:не\s+могу\s+обсуждать|давайте\s+поговорим|"
    r"i\s+can(?:not|'t)\s+(?:discuss|help|assist|comply)|"
    r"cannot\s+(?:discuss|help|assist)|policy\s+violation)",
    re.I,
)


def _is_provider_refusal(text: str) -> bool:
    return bool(_REFUSAL_RE.search((text or "").strip()))


def _env_bool(name: str, default: str = "true") -> bool:
    import os

    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class SummarizeClusterResult:
    post_text: str
    used_ids: list[int]
    headline: str
    execution: AIExecutionMetadata


def _draft_response_format(*, include_headline: bool) -> dict[str, Any]:
    props: dict[str, Any] = {
        "post": {"type": "string"},
        "used_raw_post_ids": {"type": "array", "items": {"type": "integer"}},
    }
    required = ["post", "used_raw_post_ids"]
    if include_headline:
        props["headline"] = {"type": "string", "maxLength": 200}
        required.append("headline")
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "newsroom_draft",
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": props,
                "required": required,
            },
        },
    }


def _serialize_items(posts: list[RawPost]) -> str:
    payload: list[dict[str, Any]] = []
    for p in posts:
        payload.append(
            {
                "id": p.id,
                "channel": p.channel_name,
                "message_id": p.message_id,
                "text": p.text,
            }
        )
    return json.dumps(payload, ensure_ascii=False)


def _unwrap_json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        while lines and lines[-1].strip() == "":
            lines.pop()
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _maybe_count_retry(attempt: int, max_json_retries: int) -> None:
    if attempt < max_json_retries:
        inc("openai_retries")


def _dedupe_used_ids(used: list[int], valid_ids: set[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for i in used:
        if i not in valid_ids or i in seen:
            continue
        seen.add(i)
        out.append(i)
    return out


async def _retry_backoff_sleep(attempt: int) -> None:
    from app.openai_circuit import get_openai_circuit

    delay = get_openai_circuit().backoff_delay_sec(attempt)
    await asyncio.sleep(delay)


async def summarize_cluster(
    client: AsyncOpenAI,
    *,
    settings: Settings,
    model: str,
    posts: list[RawPost],
    max_json_retries: int = 3,
    request_timeout_sec: float = 90.0,
    log_chat_latency: bool = True,
) -> SummarizeClusterResult:
    from app.openai_circuit import get_openai_circuit

    circuit = get_openai_circuit()
    if not circuit.allow_request():
        inc("openai_failures")
        raise SummarizerError("OpenAI circuit open (OPENAI_DISABLED)")

    if not posts:
        raise SummarizerError("No posts to summarize")

    valid_ids = {p.id for p in posts}
    digest_on = digest_prompt_active(settings, posts)
    from app.editorial.source_languages import translation_context_for_cluster

    lang_ctx = translation_context_for_cluster(posts, settings)
    user_prompt = build_user_prompt(
        settings,
        _serialize_items(posts),
        digest_active=digest_on,
        source_language=lang_ctx["source_language"],
        output_language=lang_ctx["output_language"],
    )
    system_prompt = build_system_prompt(
        settings,
        source_language=lang_ctx["source_language"],
        output_language=lang_ctx["output_language"],
    )
    include_headline = settings.headline_mode == "json"
    response_format = _draft_response_format(include_headline=include_headline)
    prompt_ref = resolve_cluster_draft_prompt(settings)

    def _parse_completion(
        completion: Any,
        *,
        api_sec: float,
        attempt: int,
    ) -> SummarizeClusterResult | None:
        choice = completion.choices[0].message.content
        if not choice or not choice.strip():
            log_event(logger, "openai.empty_content", attempt=attempt)
            return None

        unwrapped = _unwrap_json_text(choice)
        if not unwrapped.startswith("{") or not unwrapped.endswith("}"):
            log_event(logger, "openai.non_json_shape", attempt=attempt, sample=unwrapped[:200])
            return None

        try:
            data = json.loads(unwrapped)
        except json.JSONDecodeError as exc:
            log_event(logger, "openai.json_decode_failed", attempt=attempt, error=str(exc), sample=unwrapped[:400])
            return None

        if not include_headline and isinstance(data, dict) and "headline" not in data:
            data = {**data, "headline": ""}

        try:
            parsed = OpenAIClusterResponse.model_validate(data)
        except ValidationError as exc:
            log_event(logger, "openai.payload_invalid", attempt=attempt, error=str(exc)[:400])
            return None

        used_ids = _dedupe_used_ids(parsed.used_raw_post_ids, valid_ids)
        from app.publisher.draft_builder import finalize_draft_content

        post_text = finalize_draft_content(parsed.post, max_chars=settings.max_post_chars)
        headline = (parsed.headline if include_headline else "").strip()
        if headline:
            from app.publisher.draft_builder import strip_source_attribution

            headline = strip_source_attribution(headline)

        if not used_ids:
            if post_text and valid_ids:
                used_ids = sorted(valid_ids)
                log_event(logger, "openai.draft_ids_defaulted", attempt=attempt, used_ids=len(used_ids))
            else:
                log_event(logger, "openai.draft_no_valid_ids", attempt=attempt)
                return None

        if not post_text:
            log_event(logger, "openai.empty_post_with_ids", attempt=attempt)
            return None

        log_event(
            logger,
            "openai.draft_parsed_ok",
            attempt=attempt,
            used_ids=len(used_ids),
            post_len=len(post_text),
            digest_mode=digest_on,
            headline_mode=settings.headline_mode,
        )
        usage = getattr(completion, "usage", None)
        pin = getattr(usage, "prompt_tokens", None) if usage else None
        pout = getattr(usage, "completion_tokens", None) if usage else None
        in_tok = int(pin) if pin is not None else None
        out_tok = int(pout) if pout is not None else None
        tot_tok = (in_tok + out_tok) if in_tok is not None and out_tok is not None else None
        cost: float | None = None
        if in_tok is not None and out_tok is not None:
            cost = estimate_chat_cost_usd(model=model, input_tokens=in_tok, output_tokens=out_tok)
        safety = tuple(scan_draft_output(post_text, headline=headline))
        exec_meta = AIExecutionMetadata(
            prompt_id=prompt_ref.prompt_id,
            prompt_version=prompt_ref.prompt_version,
            prompt_fingerprint=prompt_ref.fingerprint,
            model=model,
            latency_sec=float(api_sec),
            retry_count=max(0, attempt - 1),
            input_tokens=in_tok,
            output_tokens=out_tok,
            total_tokens=tot_tok,
            estimated_cost_usd=cost,
            completed_at_unix=time.time(),
            safety_warnings=safety,
        )
        inc("ai_cluster_calls")
        if in_tok is not None and in_tok > 0:
            inc("ai_input_tokens", in_tok)
        if out_tok is not None and out_tok > 0:
            inc("ai_output_tokens", out_tok)
        if cost is not None and cost > 0:
            inc("ai_cost_micro_usd", int(cost * 1_000_000))
        set_gauge("ai_last_cluster_latency_sec", float(api_sec))
        try:
            from ops.economics.budgets import record_ai_usage
            from ops.economics.resource_accounting import record_resource

            rd = getattr(settings, "runtime_state_dir", None) or __import__("os").getenv("RUNTIME_STATE_DIR", "var/runtime")
            record_ai_usage(rd, tokens=tot_tok or 0, requests=1, cost_usd=float(cost or 0))
            record_resource(
                rd,
                stage="summarize",
                duration_sec=float(api_sec),
                tokens=tot_tok or 0,
                cost_usd=float(cost or 0),
                count=1,
            )
        except Exception:
            pass
        circuit.record_success()
        return SummarizeClusterResult(post_text=post_text, used_ids=used_ids, headline=headline, execution=exec_meta)

    async def _recovery_after_refusal() -> SummarizeClusterResult | None:
        if not _env_bool("OPENAI_REFUSAL_RECOVERY_ENABLED", "true"):
            return None
        from ai.editorial import build_refusal_recovery_system_prompt, build_refusal_recovery_user_prompt

        recovery_system = build_refusal_recovery_system_prompt(settings)
        recovery_user = build_refusal_recovery_user_prompt(
            settings,
            _serialize_items(posts),
            source_language=lang_ctx["source_language"],
            output_language=lang_ctx["output_language"],
        )
        log_event(logger, "openai.refusal_recovery_attempt", model=model)
        try:
            completion, api_sec = await _chat(
                model=model,
                temperature=0.0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": recovery_system},
                    {"role": "user", "content": recovery_user},
                ],
            )
        except Exception as exc:
            log_event(logger, "openai.refusal_recovery_failed", error=repr(exc)[:200])
            return None
        parsed = _parse_completion(completion, api_sec=api_sec, attempt=0)
        if parsed is not None:
            log_event(logger, "openai.refusal_recovery_ok", post_len=len(parsed.post_text))
        return parsed

    async def _chat(**kwargs: Any) -> tuple[Any, float]:
        t0 = time.perf_counter()
        try:
            out = await asyncio.wait_for(
                client.chat.completions.create(**kwargs),
                timeout=request_timeout_sec,
            )
            dt = time.perf_counter() - t0
            if log_chat_latency:
                log_event(
                    logger,
                    "openai.chat_completion_duration_sec",
                    duration_sec=round(dt, 4),
                    model=model,
                )
            return out, dt
        except asyncio.CancelledError:
            log_event(logger, "openai.request_cancelled", model=model)
            raise

    last_err: str | None = None
    refusal_seen = False
    for attempt in range(1, max_json_retries + 1):
        try:
            completion, api_sec = await _chat(
                model=model,
                temperature=0.1,
                response_format=response_format,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except APIStatusError as exc:
            if getattr(exc, "status_code", None) == 400:
                log_event(
                    logger,
                    "openai.response_format_fallback",
                    model=model,
                    detail=str(exc)[:400],
                )
                try:
                    completion, api_sec = await _chat(
                        model=model,
                        temperature=0.1,
                        response_format={"type": "json_object"},
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                    )
                    log_event(
                        logger,
                        "openai.recovery_json_object_success",
                        attempt=attempt,
                        model=model,
                    )
                except asyncio.TimeoutError:
                    log_event(logger, "openai.request_timeout", attempt=attempt, phase="json_object_fallback")
                    last_err = "timeout"
                    _maybe_count_retry(attempt, max_json_retries)
                    await _retry_backoff_sleep(attempt)
                    continue
                except Exception as exc2:
                    log_event(logger, "openai.request_failed", attempt=attempt, error=repr(exc2))
                    last_err = repr(exc2)
                    _maybe_count_retry(attempt, max_json_retries)
                    await _retry_backoff_sleep(attempt)
                    continue
            else:
                log_event(logger, "openai.request_failed", attempt=attempt, error=repr(exc))
                last_err = repr(exc)
                _maybe_count_retry(attempt, max_json_retries)
                await _retry_backoff_sleep(attempt)
                continue
        except asyncio.TimeoutError:
            log_event(logger, "openai.request_timeout", attempt=attempt, phase="primary")
            last_err = "timeout"
            _maybe_count_retry(attempt, max_json_retries)
            await _retry_backoff_sleep(attempt)
            continue
        except Exception as exc:
            log_event(logger, "openai.request_failed", attempt=attempt, error=repr(exc))
            last_err = repr(exc)
            _maybe_count_retry(attempt, max_json_retries)
            await _retry_backoff_sleep(attempt)
            continue

        choice = completion.choices[0].message.content
        if not choice or not choice.strip():
            last_err = "empty_content"
            _maybe_count_retry(attempt, max_json_retries)
            continue

        unwrapped = _unwrap_json_text(choice)
        if not unwrapped.startswith("{") or not unwrapped.endswith("}"):
            if _is_provider_refusal(unwrapped):
                refusal_seen = True
            last_err = "non_json_shape"
            _maybe_count_retry(attempt, max_json_retries)
            continue

        parsed = _parse_completion(completion, api_sec=api_sec, attempt=attempt)
        if parsed is not None:
            return parsed
        last_err = "parse_failed"
        _maybe_count_retry(attempt, max_json_retries)
        continue

    if refusal_seen:
        recovered = await _recovery_after_refusal()
        if recovered is not None:
            return recovered

    inc("openai_failures")
    inc("ai_cluster_failures")
    circuit.record_failure(last_err or "summarize_exhausted")
    raise SummarizerError(f"OpenAI summarization failed after retries: {last_err}")
