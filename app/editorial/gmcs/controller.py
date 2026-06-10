"""GMCS controller — competitive ecosystem simulation."""

from __future__ import annotations

from typing import Any

from app.editorial.gmcs.competitive_simulator import simulate_ecosystem_competition
from app.editorial.gmcs.config import gmcs_enabled
from app.editorial.gmcs.market_dominance_index import compute_market_dominance
from app.editorial.gmcs.state import record_gmcs_evaluation


def _vertical_from_layers(layer_extras: dict[str, Any]) -> str:
    mpaes = layer_extras.get("mpaes") if isinstance(layer_extras.get("mpaes"), dict) else {}
    hub = mpaes.get("hub_substitution") if isinstance(mpaes.get("hub_substitution"), dict) else {}
    if hub.get("vertical"):
        return str(hub["vertical"])
    ccd = layer_extras.get("ccd") if isinstance(layer_extras.get("ccd"), dict) else {}
    return str(ccd.get("category") or "macro")


def run_gmcs_competitive_analysis(
    body: str,
    *,
    runtime_dir: str | None,
    layer_extras: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if not gmcs_enabled():
        return body, {}

    ugsol = layer_extras.get("ugsol") if isinstance(layer_extras.get("ugsol"), dict) else {}
    imri = ugsol.get("imri") if isinstance(ugsol.get("imri"), dict) else {}
    mpaes = layer_extras.get("mpaes") if isinstance(layer_extras.get("mpaes"), dict) else {}
    peos = layer_extras.get("product_os") if isinstance(layer_extras.get("product_os"), dict) else {}
    cse = peos.get("channel_substitution") if isinstance(peos.get("channel_substitution"), dict) else {}

    vertical = _vertical_from_layers(layer_extras)
    sub = float(cse.get("substitution_score") or 50.0)
    dual = float(mpaes.get("dual_audience_trust") or 0.5)
    imri_score = float(imri.get("score") or 50.0)
    cross = len(body or "") >= 200 and sub >= 65

    sim = simulate_ecosystem_competition(
        vertical=vertical,
        substitution_score=sub,
        dual_audience_trust=dual,
        imri_score=imri_score,
        cross_domain=cross,
    )
    dominance = compute_market_dominance(sim, imri_score=imri_score)

    record_gmcs_evaluation(
        runtime_dir,
        mdi=dominance.index,
        channels_substituted=sim.channels_substituted_estimate,
        vertical=vertical,
        published=False,
    )

    out: dict[str, Any] = {
        "gmcs": {
            "enabled": True,
            "ecosystem_simulation": sim.to_dict(),
            "market_dominance": dominance.to_dict(),
            "competitive_posture": dominance.recommended_posture,
            "objective": "channel_vs_telegram_ecosystem",
        },
    }

    if dominance.tier.value == "ecosystem_leader":
        out["priority_boost"] = True
    if sim.channels_substituted_estimate >= 4:
        out["growth"] = {
            **(layer_extras.get("growth") if isinstance(layer_extras.get("growth"), dict) else {}),
            "gmcs_substitution_win": True,
            "channels_vs_ecosystem": sim.channels_substituted_estimate,
        }

    return body, out
