"""Final editorial safety gate immediately before channel publish."""

from __future__ import annotations

import json
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
) -> FinalPublishGateVerdict:
    """
    REJECT: low trust, sensational tone, governance auto-block, public output lock violation.
    MANUAL: geopolitics, rumors, soft launch, newsroom_product flag.
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
    from app.editorial.content_quality import is_incomplete_teaser

    if is_incomplete_teaser(text):
        v = FinalPublishGateVerdict(
            allowed=False,
            manual_review_required=False,
            permanent_block=True,
            reason="incomplete_teaser_no_body",
        )
        log_gate_decision(draft_id=draft_id, verdict=v)
        return v

    chans = _parse_channels(sources)
    runtime_dir = getattr(settings, "runtime_state_dir", None) if settings else None

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

    if manual and not operator_approved:
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
