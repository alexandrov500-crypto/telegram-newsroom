"""EML controller — editorial monetization without spam."""

from __future__ import annotations

from typing import Any

from app.editorial.eml.attention_value_model import compute_attention_value
from app.editorial.eml.config import eml_enabled
from app.editorial.eml.editorial_monetization_gate import evaluate_editorial_monetization_gate
from app.editorial.eml.revenue_abstraction import abstract_revenue_potential
from app.editorial.eml.state import record_eml_evaluation


def enrich_with_editorial_monetization(
    body: str,
    *,
    runtime_dir: str | None,
    layer_extras: dict[str, Any],
    editorial_category: str = "macro",
    is_breaking: bool = False,
) -> tuple[str, dict[str, Any]]:
    if not eml_enabled():
        return body, {}

    final = layer_extras.get("final_editorial_decision") if isinstance(layer_extras.get("final_editorial_decision"), dict) else {}
    publish_ok = bool(final.get("publish", True))
    ugsol = layer_extras.get("ugsol") if isinstance(layer_extras.get("ugsol"), dict) else {}
    imri = ugsol.get("imri") if isinstance(ugsol.get("imri"), dict) else {}
    mpaes = layer_extras.get("mpaes") if isinstance(layer_extras.get("mpaes"), dict) else {}
    peos = layer_extras.get("product_os") if isinstance(layer_extras.get("product_os"), dict) else {}
    gmcs = layer_extras.get("gmcs") if isinstance(layer_extras.get("gmcs"), dict) else {}
    ccd = layer_extras.get("ccd") if isinstance(layer_extras.get("ccd"), dict) else {}

    cse = peos.get("channel_substitution") if isinstance(peos.get("channel_substitution"), dict) else {}
    ref = peos.get("virality_v2") if isinstance(peos.get("virality_v2"), dict) else {}
    mdi = gmcs.get("market_dominance") if isinstance(gmcs.get("market_dominance"), dict) else {}

    attention = compute_attention_value(
        substitution_score=float(cse.get("substitution_score") or 50.0),
        imri_score=float(imri.get("score") or 50.0),
        dual_audience_trust=float(mpaes.get("dual_audience_trust") or 0.5),
        forward_prediction=float(ref.get("forward_prediction") or 0.0),
        experience_fit=float(ccd.get("experience_fit") or 0.5),
        is_breaking=is_breaking,
    )

    revenue = abstract_revenue_potential(
        attention,
        editorial_category=editorial_category,
        is_breaking=is_breaking,
        mdi_score=float(mdi.get("index") or 50.0),
    )

    gate = evaluate_editorial_monetization_gate(
        revenue,
        cognitive_value=attention.cognitive_value_score,
        publish_approved=publish_ok,
    )

    record_eml_evaluation(
        runtime_dir,
        cognitive_value=attention.cognitive_value_score,
        value_index=revenue.estimated_value_index,
        monetization_allowed=gate.allow_monetization,
        published=False,
    )

    w5_bridge: dict[str, Any] = {}
    try:
        from app.monetization.revenue_engine import score_monetization_eligibility

        elig = score_monetization_eligibility(
            body,
            vertical=editorial_category,
            insight_score=attention.cognitive_value_score,
            style_score=attention.trust_accumulation,
            signal_score=attention.substitution_value,
            is_breaking=is_breaking,
        )
        w5_bridge = {
            "w5_eligibility_score": elig.score,
            "w5_primary_stream": elig.primary_stream.value,
            "w5_sponsor_safe": elig.sponsor_safe and gate.allow_sponsor,
        }
    except Exception:
        pass

    return body, {
        "eml": {
            "enabled": True,
            "attention_value": attention.to_dict(),
            "revenue_abstraction": revenue.to_dict(),
            "monetization_gate": gate.to_dict(),
            "w5_bridge": w5_bridge,
            "objective": "attention_value_revenue_without_editorial_spam",
        },
        "editorial_monetization": {
            "allowed": gate.allow_monetization,
            "mode": revenue.mode.value,
            "cognitive_value": attention.cognitive_value_score,
        },
    }
