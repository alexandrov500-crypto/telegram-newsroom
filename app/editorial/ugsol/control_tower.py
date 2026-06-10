"""Real-time editorial control tower — sole publish authority."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.ugsol.audience_dominance_balancer import evaluate_audience_balance
from app.editorial.ugsol.content_flow_governor import ForcedMode, evaluate_content_flow
from app.editorial.ugsol.feedback_reinjection import compute_feedback_adjustments
from app.editorial.ugsol.imri import IMRIMode, compute_imri
from app.editorial.ugsol.objective_function import compute_system_objective
from app.editorial.ugsol.state import record_control_tower_decision


class EditorialMode(str, Enum):
    SIGNAL = "signal"
    CONTEXT = "context"
    DIGEST = "digest"
    EXPLAINER = "explainer"
    SYNTHESIS = "synthesis"


class PriorityLevel(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    FLAGSHIP = "flagship"


class AudienceTarget(str, Enum):
    MALE_HUB = "male_hub"
    FEMALE_HUB = "female_hub"
    UNIFIED = "unified"


class GrowthAction(str, Enum):
    FORWARD_BOOST = "forward_boost"
    HABIT_BOOST = "habit_boost"
    NONE = "none"


@dataclass(frozen=True)
class FinalEditorialDecision:
    publish: bool
    mode: EditorialMode
    priority_level: PriorityLevel
    audience_target: AudienceTarget
    growth_action: GrowthAction
    reasoning_chain: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "publish": self.publish,
            "mode": self.mode.value,
            "priority_level": self.priority_level.value,
            "audience_target": self.audience_target.value,
            "growth_action": self.growth_action.value,
            "reasoning_chain": list(self.reasoning_chain),
            "authority": "ugsol_control_tower_final",
        }


def _extract(layer_extras: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    cur: Any = layer_extras
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def _layer_signal(layer_extras: dict[str, Any]) -> dict[str, Any]:
    osgcp = layer_extras.get("osgcp") if isinstance(layer_extras.get("osgcp"), dict) else {}
    osgcp_dec = osgcp.get("editorial_decision") if isinstance(osgcp.get("editorial_decision"), dict) else {}
    ccd = layer_extras.get("ccd") if isinstance(layer_extras.get("ccd"), dict) else {}
    if not ccd:
        ccd = osgcp.get("ccd_evaluation") if isinstance(osgcp.get("ccd_evaluation"), dict) else {}
    mpaes = layer_extras.get("mpaes") if isinstance(layer_extras.get("mpaes"), dict) else {}
    peos = layer_extras.get("product_os") if isinstance(layer_extras.get("product_os"), dict) else {}

    return {
        "osgcp_action": str(osgcp_dec.get("action") or "publish"),
        "osgcp_reject": bool(layer_extras.get("osgcp_reject")),
        "osgcp_format": str(osgcp.get("format_mode") or osgcp_dec.get("format_mode") or "context"),
        "osgcp_stability_override": bool(osgcp_dec.get("stability_override")),
        "force_digest": bool(layer_extras.get("force_digest_slot")),
        "priority_boost": bool(layer_extras.get("priority_boost")),
        "flagship": bool(layer_extras.get("flagship_post")),
        "synthesize": bool(layer_extras.get("osgcp_synthesize")),
        "substitution_score": _extract(layer_extras, "product_os", "channel_substitution", "substitution_score", default=50.0),
        "pg_total": _extract(layer_extras, "product_os", "product_gravity", "total", default=50.0),
        "experience_fit": float(ccd.get("experience_fit") or 0.5),
        "dual_trust": float(mpaes.get("dual_audience_trust") or 0.5),
        "mpaes_segments": mpaes.get("cognitive_segmentation") if isinstance(mpaes.get("cognitive_segmentation"), dict) else {},
        "continuity_triggered": bool((osgcp.get("continuity") or {}).get("triggered")),
        "anti_pause": bool((osgcp.get("anti_pause") or {}).get("anti_pause_active")),
        "hub_substitution": float((mpaes.get("hub_substitution") or {}).get("substitution_score") or 50.0)
        if isinstance(mpaes.get("hub_substitution"), dict)
        else 50.0,
        "forward_prediction": _extract(layer_extras, "product_os", "virality_v2", "forward_prediction", default=0.0),
        "primary_segment": str(mpaes.get("primary_segment") or "reference_operator_male"),
    }


def resolve_final_editorial_decision(
    layer_extras: dict[str, Any],
    *,
    runtime_dir: str | None = None,
    publishing_mode: str = "core",
    newsroom_tz: str = "Europe/Moscow",
    is_breaking: bool = False,
) -> tuple[FinalEditorialDecision, dict[str, Any]]:
    sig = _layer_signal(layer_extras)
    trace: list[str] = ["ugsol:control_tower_entry"]

    balance = evaluate_audience_balance(mpaes_segments=sig["mpaes_segments"])
    trace.append(f"audience_balance:{balance.correction_action.value}")

    imri = compute_imri(
        runtime_dir=runtime_dir,
        substitution_rate=max(sig["substitution_score"], sig["hub_substitution"]),
        forward_rate=min(1.0, sig["forward_prediction"] / 100.0),
        save_rate=0.0,
        return_frequency=0.55,
        cross_domain_coverage=min(1.0, sig["substitution_score"] / 100.0),
        male_resonance=balance.male_weight,
        female_resonance=balance.female_weight,
    )
    trace.append(f"imri:{imri.score:.1f}:{imri.mode.value}")

    feedback = compute_feedback_adjustments(
        runtime_dir=runtime_dir,
        forward_rate=min(1.0, sig["forward_prediction"] / 100.0),
        male_resonance=balance.male_weight,
        female_resonance=balance.female_weight,
        imri_score=imri.score,
    )
    trace.extend(list(feedback.reasoning)[:2])

    proposed_mode = sig["osgcp_format"]
    if sig["force_digest"] or sig["osgcp_action"] == "digest":
        proposed_mode = "digest"
    if sig["synthesize"]:
        proposed_mode = "synthesis"

    flow = evaluate_content_flow(
        runtime_dir=runtime_dir,
        newsroom_tz=newsroom_tz,
        proposed_mode=proposed_mode,
        is_flagship=sig["flagship"],
        is_breaking=is_breaking or sig["priority_boost"],
        starvation=sig["continuity_triggered"] or sig["anti_pause"],
        signal_overload=sig["pg_total"] >= 85 and proposed_mode == "signal",
    )
    trace.append(f"flow:{flow.reason}")

    continuity = 0.85 if not sig["anti_pause"] else 0.55
    objective = compute_system_objective(
        substitution_score=max(sig["substitution_score"], sig["hub_substitution"]),
        forward_rate=min(1.0, sig["forward_prediction"] / 100.0),
        return_frequency=0.55,
        dual_audience_trust=sig["dual_trust"],
        continuity_score=continuity,
    )
    trace.append(f"objective:{objective.composite_score:.3f}")

    mode = EditorialMode.CONTEXT
    if flow.forced_mode_override != ForcedMode.NONE:
        mode = EditorialMode(flow.forced_mode_override.value)
    elif proposed_mode in {m.value for m in EditorialMode}:
        mode = EditorialMode(proposed_mode)

    priority = PriorityLevel.NORMAL
    if sig["flagship"] or sig["pg_total"] >= 85:
        priority = PriorityLevel.FLAGSHIP
    elif sig["priority_boost"] or is_breaking:
        priority = PriorityLevel.HIGH
    elif imri.mode == IMRIMode.RECOVERY:
        priority = PriorityLevel.LOW

    audience = AudienceTarget.UNIFIED
    if balance.correction_action.value == "boost_female_framing":
        audience = AudienceTarget.FEMALE_HUB
    elif balance.correction_action.value == "boost_male_framing":
        audience = AudienceTarget.MALE_HUB
    elif sig["primary_segment"] == "hub_female":
        audience = AudienceTarget.FEMALE_HUB
    elif sig["primary_segment"] in {"hub_male", "reference_operator_male"}:
        audience = AudienceTarget.MALE_HUB

    growth = GrowthAction.NONE
    if imri.mode == IMRIMode.DOMINANCE and sig["forward_prediction"] >= 60:
        growth = GrowthAction.FORWARD_BOOST
    elif sig["experience_fit"] >= 0.6 and mode == EditorialMode.DIGEST:
        growth = GrowthAction.HABIT_BOOST

    publish = True
    if not flow.allow_publish and publishing_mode == "core" and not sig["anti_pause"]:
        publish = False
        trace.append("flow:publish_blocked")

    if sig["osgcp_reject"] and publishing_mode == "core":
        if sig["osgcp_stability_override"] or sig["anti_pause"] or flow.inserted_synthesis:
            publish = True
            mode = EditorialMode.SYNTHESIS if flow.inserted_synthesis else EditorialMode.DIGEST
            trace.append("ugsol:override_osgcp_reject_continuity")
        elif objective.composite_score < 0.15 and imri.mode == IMRIMode.RECOVERY:
            publish = False
            trace.append("ugsol:reject_recovery_low_objective")
        else:
            publish = True
            mode = EditorialMode.DIGEST
            trace.append("ugsol:downgrade_osgcp_reject_to_digest")

    if imri.mode == IMRIMode.DOMINANCE and publish:
        trace.append("ugsol:dominance_mode_active")

    decision = FinalEditorialDecision(
        publish=publish,
        mode=mode,
        priority_level=priority,
        audience_target=audience,
        growth_action=growth,
        reasoning_chain=tuple(trace),
    )

    record_control_tower_decision(
        runtime_dir,
        publish=publish,
        mode=mode.value,
        priority_level=priority.value,
        imri_score=imri.score,
        objective_score=objective.composite_score,
        published=False,
    )

    meta = {
        "final_decision": decision.to_dict(),
        "audience_balance": balance.to_dict(),
        "imri": imri.to_dict(),
        "content_flow": flow.to_dict(),
        "feedback_adjustments": feedback.to_dict(),
        "system_objective": objective.to_dict(),
        "layer_signals": {
            "osgcp_action": sig["osgcp_action"],
            "osgcp_reject_advisory": sig["osgcp_reject"],
            "substitution_score": sig["substitution_score"],
            "dual_trust": sig["dual_trust"],
        },
    }
    return decision, meta
