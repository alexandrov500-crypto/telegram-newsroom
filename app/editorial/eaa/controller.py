"""EAA v2 controller — final editorial autonomy gate."""

from __future__ import annotations

from typing import Any

from app.editorial.eaa.config import eaa_enabled
from app.editorial.eaa.decision_matrix import resolve_autonomy_decision
from app.editorial.eaa.safety_envelope import evaluate_safety_envelope
from app.editorial.eaa.state import record_eaa_decision


def evaluate_editorial_autonomy_v2(
    body: str,
    *,
    runtime_dir: str | None,
    layer_extras: dict[str, Any],
    is_breaking: bool = False,
    publishing_mode: str = "core",
    newsroom_tz: str = "Europe/Moscow",
    settings: Any | None = None,
) -> tuple[str, dict[str, Any]]:
    if not eaa_enabled():
        return body, {}

    final = layer_extras.get("final_editorial_decision") if isinstance(layer_extras.get("final_editorial_decision"), dict) else {}
    tower_publish = bool(final.get("publish", True))

    ugsol = layer_extras.get("ugsol") if isinstance(layer_extras.get("ugsol"), dict) else {}
    imri = ugsol.get("imri") if isinstance(ugsol.get("imri"), dict) else {}
    flow = ugsol.get("content_flow") if isinstance(ugsol.get("content_flow"), dict) else {}
    eml = layer_extras.get("eml") if isinstance(layer_extras.get("eml"), dict) else {}
    attn = eml.get("attention_value") if isinstance(eml.get("attention_value"), dict) else {}

    safety = evaluate_safety_envelope(body, is_breaking=is_breaking)

    gap = float(flow.get("gap_minutes") or 0)
    anti_pause_active = False
    silence_recovery = False
    try:
        from app.editorial.stability.anti_pause import evaluate_anti_pause

        ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
        anti_pause_active = ap.anti_pause_active
        silence_recovery = ap.max_gap_exceeded
    except Exception:
        pass
    starvation = bool(flow.get("starvation") or flow.get("inserted_synthesis"))

    rules_approved = False
    ai_confidence = 0.0
    ai_verdict_dict: dict[str, Any] = {}
    try:
        from app.editorial.ai_editorial_reviewer import rule_based_editorial_review
        from app.editorial.content_quality import resolve_publishable_thresholds, strip_public_template_metadata

        review_body = strip_public_template_metadata(body)
        min_chars, min_sents = resolve_publishable_thresholds(
            publishing_mode=publishing_mode,
            anti_pause_active=anti_pause_active or silence_recovery,
        )
        verdict = rule_based_editorial_review(
            review_body,
            extras_json=_extras_json_stub(layer_extras),
            settings=settings,
            min_chars=min_chars,
            min_sentences=min_sents,
        )
        rules_approved = verdict.approved
        ai_confidence = float(verdict.confidence)
        ai_verdict_dict = verdict.to_dict()
    except Exception:
        rules_approved = len(body or "") >= 80
        ai_confidence = 0.65
    continuity_ok = gap < 90 or anti_pause_active or silence_recovery or starvation

    autonomy = resolve_autonomy_decision(
        control_tower_publish=tower_publish,
        safety=safety,
        rules_approved=rules_approved,
        ai_confidence=ai_confidence,
        imri_score=float(imri.get("score") or 50.0),
        cognitive_value=float(attn.get("cognitive_value_score") or 0.5),
        continuity_ok=continuity_ok,
    )

    record_eaa_decision(
        runtime_dir,
        mode=autonomy.mode.value,
        autonomous_publish=autonomy.autonomous_publish,
        confidence=autonomy.confidence,
        published=False,
    )

    out: dict[str, Any] = {
        "eaa": {
            "enabled": True,
            "autonomy_decision": autonomy.to_dict(),
            "safety_envelope": safety.to_dict(),
            "ai_editorial_review": ai_verdict_dict,
            "zero_human_ready": autonomy.mode.value == "zero_human",
            "objective": "editorial_ai_autonomy_v2",
        },
        "ai_editorial_review": {
            **ai_verdict_dict,
            "autonomous_mode": autonomy.mode.value,
            "approved": autonomy.autonomous_publish,
        },
    }

    if tower_publish and not autonomy.autonomous_publish and publishing_mode == "core":
        out["eaa_reject"] = True
        out["stability_reject"] = True
    else:
        out.pop("stability_reject", None)
        out["autonomous_publish_approved"] = autonomy.autonomous_publish

    return body, out


def _extras_json_stub(layer_extras: dict[str, Any]) -> str:
    import json

    try:
        return json.dumps(
            {
                "category": (layer_extras.get("ccd") or {}).get("category", "macro")
                if isinstance(layer_extras.get("ccd"), dict)
                else "macro",
                "editorial_confidence": {"confidence_score": 0.72},
            },
            ensure_ascii=False,
        )
    except Exception:
        return "{}"
