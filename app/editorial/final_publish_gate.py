"""Final editorial safety gate immediately before channel publish."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from app.config import Settings
from app.editorial.governance_advanced import evaluate_advanced_governance
from app.editorial.minimal_newsroom import bypass_final_publish_gate
from app.editorial.publish_gate_debug import log_gate_decision
from app.editorial.scoring_engine import score_story
from app.editorial.soft_launch import is_soft_launch_mode
from app.editorial.tone_engine import apply_newsroom_tone
from app.editorial.trust_system import evaluate_editorial_trust
from publisher.publish_formatting import build_channel_message_html


@dataclass(frozen=True)
class FinalPublishGateVerdict:
    allowed: bool
    manual_review_required: bool
    permanent_block: bool
    reason: str
    trust_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_channels(sources: str) -> list[str]:
    try:
        data = json.loads(sources or "[]")
        if not isinstance(data, list):
            return []
        return [str(x.get("channel") or "") for x in data if isinstance(x, dict) and x.get("channel")]
    except (json.JSONDecodeError, TypeError):
        return []


def _extras_require_manual(extras_json: str | None) -> bool:
    if not extras_json:
        return False
    try:
        ex = json.loads(extras_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(ex, dict):
        return False
    np = ex.get("newsroom_product")
    if isinstance(np, dict) and np.get("manual_review_required"):
        return True
    pol = np.get("publish_policy") if isinstance(np, dict) else None
    if isinstance(pol, dict) and pol.get("manual_review_required"):
        return True
    return False


def evaluate_final_publish_gate(
    *,
    content: str,
    sources: str,
    draft_extras_json: str | None = None,
    settings: Settings | None = None,
    operator_approved: bool = False,
    draft_id: int | None = None,
    safety_only: bool = False,
) -> FinalPublishGateVerdict:
    """
    REJECT: low trust, sensational tone, governance auto-block, public output lock violation.
    MANUAL: geopolitics, rumors, soft launch, newsroom_product flag.

    ``safety_only`` (publishing-floor mode): enforce ONLY content-safety checks
    (real body, advertising, output language, governance, tone, source trust,
    HTML guards, rumor/contradiction) and skip the editorial/cosmetic/marketing
    quality gates (template completeness, premium signal policy, discretionary
    review). This guarantees the channel can keep publishing trustworthy items
    even when experimental ranking/quality changes would otherwise reject every
    draft — algorithm tuning can never silence the channel.
    """
    if bypass_final_publish_gate():
        v = FinalPublishGateVerdict(
            allowed=True,
            manual_review_required=False,
            permanent_block=False,
            reason="recovery_bypass",
        )
        log_gate_decision(draft_id=draft_id, verdict=v, extra={"recovery_bypass": True})
        return v

    text = (content or "").strip()
    runtime_dir = getattr(settings, "runtime_state_dir", None) if settings else None
    from app.editorial.content_quality import is_incomplete_teaser
    from app.publisher.draft_builder import polish_channel_post

    quality_text = polish_channel_post(text, max_chars=8000)

    if is_incomplete_teaser(quality_text):
        v = FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=False,
            permanent_block=True,
            reason="incomplete_teaser_no_body",
        )
        log_gate_decision(draft_id=draft_id, verdict=v)
        return v

    # Output-language safety runs first (applies in safety-only floor mode too):
    # a CJK leak is a hard content-safety failure, not a cosmetic issue.
    from app.editorial.source_languages import publish_output_language, text_violates_output_language

    out_lang = publish_output_language(settings)
    if text_violates_output_language(text, output_language=out_lang):
        v = FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=True,
            permanent_block=False,
            reason="output_language_cjk_leak",
        )
        log_gate_decision(draft_id=draft_id, verdict=v, extra={"output_language": out_lang})
        return v

    try:
        rendered = build_channel_message_html(text, sources, draft_id=draft_id or 0, runtime_dir=runtime_dir)
        from app.editorial.content_quality import (
            has_hidden_advertising,
            is_publishably_informative,
            passes_premium_newsroom_policy,
            strip_public_template_metadata,
        )
        from publisher.public_renderer import strip_telegram_markdown

        plain_rendered = strip_telegram_markdown(re.sub(r"<[^>]+>", " ", rendered or ""))
        plain_rendered = re.sub(r"\s+", " ", plain_rendered).strip()
        if has_hidden_advertising(plain_rendered):
            v = FinalPublishGateVerdict(
                allowed=False,
                manual_review_required=False,
                permanent_block=True,
                reason="hidden_advertising",
            )
            log_gate_decision(draft_id=draft_id, verdict=v)
            return v
        plain_core = strip_public_template_metadata(plain_rendered)
        informative = is_publishably_informative(plain_core, min_chars=90, min_sentences=2) or (
            is_publishably_informative(quality_text, min_chars=90, min_sentences=2)
        )
        teaser_block = is_incomplete_teaser(plain_core) and is_incomplete_teaser(quality_text)
        if not safety_only:
            if teaser_block or not informative:
                # Recoverable, NOT permanent: a render/formatting hiccup must not
                # silently drain the queue and stall the channel. The draft stays
                # pending so a later tick (after sanitation) can re-attempt it.
                v = FinalPublishGateVerdict(
                    allowed=False,
                    manual_review_required=True,
                    permanent_block=False,
                    reason="incomplete_public_template",
                )
                log_gate_decision(draft_id=draft_id, verdict=v)
                return v
            core_informative = is_publishably_informative(plain_core, min_chars=90, min_sentences=2)
            policy_text = plain_core if core_informative else quality_text
            if not passes_premium_newsroom_policy(policy_text) and not (
                policy_text is plain_core and passes_premium_newsroom_policy(quality_text)
            ):
                v = FinalPublishGateVerdict(
                    allowed=False,
                    manual_review_required=False,
                    permanent_block=True,
                    reason="premium_policy_low_signal",
                )
                log_gate_decision(draft_id=draft_id, verdict=v)
                return v
    except Exception as exc:
        v = FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=True,
            permanent_block=False,
            reason="render_check_failed",
        )
        log_gate_decision(
            draft_id=draft_id,
            verdict=v,
            extra={"error": repr(exc)[:120]},
        )
        return v

    chans = _parse_channels(sources)
    gov = evaluate_advanced_governance(text)
    if gov.auto_block:
        return FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=False,
            permanent_block=True,
            reason=f"governance:{gov.reason}",
        )

    tone = apply_newsroom_tone(text)
    if not tone.is_acceptable:
        return FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=False,
            permanent_block=True,
            reason="sensational_tone",
        )

    escore = score_story(text=text, sources=chans, runtime_dir=runtime_dir)
    trust = evaluate_editorial_trust(text, escore, sources=chans, runtime_dir=runtime_dir)

    if not safety_only:
        from app.editorial.trust_mode import evaluate_trust_mode

        tm = evaluate_trust_mode(
            text,
            sources=chans,
            runtime_dir=runtime_dir,
            settings=settings,
            operator_approved=operator_approved,
        )
        if not tm.allowed:
            v = FinalPublishGateVerdict(
                allowed=False,
                manual_review_required=tm.manual_review_required,
                permanent_block=tm.permanent_block,
                reason=f"trust_mode:{tm.reason}",
                trust_score=trust.trust_score,
            )
            log_gate_decision(draft_id=draft_id, verdict=v, extra={"trust_mode": tm.to_dict()})
            return v

        from app.editorial.publication_risk_score import score_publication_risk

        risk = score_publication_risk(text, sources=chans, runtime_dir=runtime_dir)
        if risk.mandatory_review and not operator_approved:
            v = FinalPublishGateVerdict(
                allowed=False,
                manual_review_required=True,
                permanent_block=False,
                reason=f"publication_risk:{risk.score:.2f}",
                trust_score=trust.trust_score,
            )
            log_gate_decision(draft_id=draft_id, verdict=v, extra={"risk": risk.to_dict()})
            return v

        from app.editorial.staging_mode import evaluate_staging_publish_gate

        staging = evaluate_staging_publish_gate(
            sources=chans,
            runtime_dir=runtime_dir,
            settings=settings,
            operator_approved=operator_approved,
            draft_id=draft_id,
        )
        if not staging.allowed:
            v = FinalPublishGateVerdict(
                allowed=False,
                manual_review_required=staging.manual_review_required,
                permanent_block=False,
                reason=f"staging:{staging.reason}",
                trust_score=trust.trust_score,
            )
            log_gate_decision(draft_id=draft_id, verdict=v, extra={"staging": staging.to_dict()})
            return v

    if trust.rumor_risk >= 0.65 and len(set(chans)) < 2:
        return FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=True,
            permanent_block=False,
            reason="rumor_single_source",
            trust_score=trust.trust_score,
        )

    if trust.source_contradiction:
        return FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=True,
            permanent_block=False,
            reason="conflicting_sources",
            trust_score=trust.trust_score,
        )

    if trust.trust_score < 0.45:
        return FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=False,
            permanent_block=True,
            reason="low_trust_score",
            trust_score=trust.trust_score,
        )

    runtime = getattr(settings, "runtime_state_dir", None) if settings else None
    html = build_channel_message_html(text, sources, draft_id=0, runtime_dir=runtime)
    from app.editorial.publish_pipeline_guards import enforce_publish_html_guards

    try:
        enforce_publish_html_guards(html, draft_id=draft_id, settings=settings)
    except ValueError as exc:
        reason = str(exc)
        v = FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=False,
            permanent_block=True,
            reason=reason[:120],
            trust_score=trust.trust_score,
        )
        log_gate_decision(draft_id=draft_id, verdict=v, extra={"guard": reason})
        return v

    manual = (
        trust.manual_review_required
        or gov.manual_review
        or _extras_require_manual(draft_extras_json)
        or is_soft_launch_mode()
    )

    if manual and not operator_approved and not safety_only:
        reason = "manual_review_required"
        if is_soft_launch_mode():
            reason = "soft_launch_manual_review"
        elif trust.manual_review_required:
            reason = f"trust_manual:{','.join(trust.reasons[:2]) or 'low_corroboration'}"
        elif gov.manual_review:
            reason = f"governance_manual:{gov.reason}"
        v = FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=True,
            permanent_block=False,
            reason=reason,
            trust_score=trust.trust_score,
        )
        log_gate_decision(draft_id=draft_id, verdict=v, extra={"trust": trust.to_dict(), "gov": gov.reason})
        return v

    v = FinalPublishGateVerdict(
        allowed=True,
        manual_review_required=False,
        permanent_block=False,
        reason="ok",
        trust_score=trust.trust_score,
    )
    log_gate_decision(draft_id=draft_id, verdict=v)
    return v
