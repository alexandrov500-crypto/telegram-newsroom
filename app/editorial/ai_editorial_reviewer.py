"""AI + rules editorial review for autonomous publish (no human moderation)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiEditorialVerdict:
    approved: bool
    confidence: float
    reason: str
    expert_notes: str
    source: str  # openai | rules | hybrid

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def autonomous_editorial_mode_enabled() -> bool:
    return os.getenv("AUTONOMOUS_EDITORIAL_MODE", "false").strip().lower() in ("1", "true", "yes", "on")


def _min_ai_confidence() -> float:
    try:
        return max(0.5, min(0.95, float(os.getenv("AI_EDITORIAL_MIN_CONFIDENCE", "0.68"))))
    except ValueError:
        return 0.68


def _rules_fallback_verdict(rules: AiEditorialVerdict, *, reason_code: str) -> AiEditorialVerdict:
    """
    When rule-based review already passed, autonomous mode must not block publish
    because OpenAI returned empty/invalid JSON or is temporarily unavailable.
    """
    if not rules.approved:
        return AiEditorialVerdict(False, rules.confidence, "openai_error_rules_insufficient", "", "rules")
    min_conf = _min_ai_confidence()
    if autonomous_editorial_mode_enabled() or rules.confidence >= min_conf:
        conf = round(min(0.92, max(rules.confidence, min_conf if autonomous_editorial_mode_enabled() else rules.confidence)), 4)
        return AiEditorialVerdict(True, conf, reason_code, rules.expert_notes, "rules")
    return AiEditorialVerdict(False, rules.confidence, "openai_error_rules_insufficient", "", "rules")


def _ai_review_enabled() -> bool:
    return os.getenv("AI_EDITORIAL_REVIEW_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def extras_ai_approves_autonomous_publish(extras_json: str | None) -> bool:
    if not autonomous_editorial_mode_enabled():
        return False
    try:
        detail = json.loads(extras_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(detail, dict):
        return False
    ai = detail.get("ai_editorial_review") or {}
    if not isinstance(ai, dict) or not ai.get("approved"):
        return False
    try:
        conf = float(ai.get("confidence") or 0.0)
    except (TypeError, ValueError):
        conf = 0.0
    return conf >= _min_ai_confidence()


def rule_based_editorial_review(
    content: str,
    *,
    sources: str = "[]",
    extras_json: str = "{}",
    settings: Any | None = None,
    min_chars: int | None = None,
    min_sentences: int | None = None,
) -> AiEditorialVerdict:
    from app.editorial.content_quality import is_publishably_informative, strip_public_template_metadata

    text = strip_public_template_metadata((content or "").strip())
    if not text:
        return AiEditorialVerdict(False, 0.0, "empty_content", "", "rules")

    chars_floor = 80 if min_chars is None else min_chars
    sents_floor = 2 if min_sentences is None else min_sentences
    if not is_publishably_informative(text, min_chars=chars_floor, min_sentences=sents_floor):
        return AiEditorialVerdict(False, 0.2, "not_informative", "", "rules")

    runtime_dir = getattr(settings, "runtime_state_dir", None) if settings else os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    vertical = "general"
    is_breaking = False
    try:
        ex = json.loads(extras_json or "{}")
        vertical = str(ex.get("category") or (ex.get("editorial_tags") or {}).get("category") or "general")
        is_breaking = bool((ex.get("breaking") or {}).get("is_breaking"))
    except (json.JSONDecodeError, TypeError):
        ex = {}

    try:
        from app.flywheel.pipeline import evaluate_pre_publish_editorial

        w3 = evaluate_pre_publish_editorial(
            text,
            settings=settings,
            runtime_dir=str(runtime_dir or ""),
            vertical=vertical,
            is_breaking=is_breaking,
        )
        if not w3.allowed:
            return AiEditorialVerdict(False, 0.35, f"w3:{w3.reason}", "", "rules")
    except Exception:
        pass

    if settings is not None:
        try:
            from app.editorial.final_publish_gate import evaluate_final_publish_gate

            gate = evaluate_final_publish_gate(
                content=text,
                sources=sources,
                draft_extras_json=extras_json,
                settings=settings,
                operator_approved=autonomous_editorial_mode_enabled(),
                draft_id=None,
                safety_only=False,
            )
            if not gate.allowed:
                if gate.permanent_block:
                    return AiEditorialVerdict(False, 0.25, gate.reason, "", "rules")
                if gate.manual_review_required and not autonomous_editorial_mode_enabled():
                    return AiEditorialVerdict(False, 0.45, f"manual:{gate.reason}", "", "rules")
        except Exception as exc:
            log_event(logger, "ai_editorial.rule_gate_skipped", error=repr(exc)[:120])

    conf = 0.72
    try:
        ex = json.loads(extras_json or "{}")
        block = ex.get("editorial_confidence") or {}
        if isinstance(block, dict):
            conf = float(block.get("confidence_score") or block.get("total") or conf)
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return AiEditorialVerdict(
        True,
        round(min(0.92, max(0.55, conf)), 4),
        "rules_pass",
        "Rule-based editorial checks passed.",
        "rules",
    )


async def ai_editorial_review(
    content: str,
    *,
    sources: str = "[]",
    extras_json: str = "{}",
    settings: Any | None = None,
    openai_client: Any | None = None,
) -> AiEditorialVerdict:
    """OpenAI expert review when available; always runs rule-based guard first."""
    rules = rule_based_editorial_review(content, sources=sources, extras_json=extras_json, settings=settings)
    if not rules.approved:
        log_event(logger, "ai_editorial.rejected", source="rules", reason=rules.reason)
        return rules

    if not _ai_review_enabled() or openai_client is None:
        if rules.confidence >= _min_ai_confidence():
            return rules
        return _rules_fallback_verdict(rules, reason_code="rules_autonomous_no_openai")

    try:
        from app.config import Settings as AppSettings

        model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        if isinstance(settings, AppSettings):
            model = getattr(settings, "openai_model", model) or model

        lang = os.getenv("PUBLISH_OUTPUT_LANGUAGE", "ru").strip().lower()
        sys_prompt = (
            "You are the chief editor of an autonomous financial newsroom. "
            "Review the draft for factual tone, news value, no hype/advertising, no unverified rumors. "
            f"Output language context: {lang}. "
            "Respond ONLY with JSON: "
            '{"approved": bool, "confidence": 0-1, "reason": "short code", "expert_notes": "1 sentence"}'
        )
        user = f"DRAFT:\n{(content or '')[:3500]}\n\nSOURCES:\n{(sources or '')[:1200]}"

        resp = await openai_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=280,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        if not raw:
            raise ValueError("empty_openai_response")
        data = json.loads(raw)
        approved = bool(data.get("approved"))
        conf = float(data.get("confidence") or 0.0)
        reason = str(data.get("reason") or "ai_review")[:64]
        notes = str(data.get("expert_notes") or "")[:400]

        if not approved or conf < _min_ai_confidence():
            v = AiEditorialVerdict(False, conf, reason or "ai_rejected", notes, "openai")
            log_event(logger, "ai_editorial.rejected", source="openai", reason=v.reason, confidence=conf)
            return v

        v = AiEditorialVerdict(True, conf, reason or "ai_approved", notes, "hybrid")
        log_event(logger, "ai_editorial.approved", source="hybrid", confidence=conf, reason=reason)
        return v
    except Exception as exc:
        log_event(logger, "ai_editorial.openai_failed", error=repr(exc)[:200])
        return _rules_fallback_verdict(rules, reason_code="rules_fallback_openai_error")
