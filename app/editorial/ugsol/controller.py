"""UGSOL controller — final orchestration after full intelligence stack."""

from __future__ import annotations

from typing import Any

from app.editorial.ugsol.config import ugsol_enabled
from app.editorial.ugsol.control_tower import FinalEditorialDecision, resolve_final_editorial_decision


def run_ugsol_control_tower(
    body: str,
    *,
    runtime_dir: str | None,
    layer_extras: dict[str, Any],
    publishing_mode: str = "core",
    newsroom_tz: str = "Europe/Moscow",
    is_breaking: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Single publish authority — all layers provide signals, tower decides."""
    if not ugsol_enabled():
        return body, {}

    decision, meta = resolve_final_editorial_decision(
        layer_extras,
        runtime_dir=runtime_dir,
        publishing_mode=publishing_mode,
        newsroom_tz=newsroom_tz,
        is_breaking=is_breaking,
    )

    out: dict[str, Any] = {
        "ugsol": {
            **meta,
            "enabled": True,
            "shipping_authority": "ugsol_control_tower",
            "pipeline_position": "post_osgcp_ccd_final",
            "objective": "autonomous_cognitive_media_replacement_engine",
        },
        "final_editorial_decision": decision.to_dict(),
    }

    if not decision.publish and publishing_mode == "core":
        out["ugsol_reject"] = True
        out["stability_reject"] = True
    else:
        out.pop("stability_reject", None)
        out.pop("osgcp_reject", None)
        out.pop("ueos_reject", None)
        out.pop("product_os_reject", None)

    if decision.mode.value in {"digest", "synthesis"}:
        out["force_digest_slot"] = True
    if decision.mode.value == "synthesis":
        out["ugsol_synthesize"] = True
    if decision.priority_level.value in {"high", "flagship"}:
        out["priority_boost"] = True
    if decision.priority_level.value == "flagship":
        out["flagship_post"] = True
    if decision.growth_action.value == "forward_boost":
        out["growth"] = {
            **(layer_extras.get("growth") if isinstance(layer_extras.get("growth"), dict) else {}),
            "ugsol_forward_boost": True,
        }
    if decision.growth_action.value == "habit_boost":
        out["growth"] = {
            **(layer_extras.get("growth") if isinstance(layer_extras.get("growth"), dict) else {}),
            "ugsol_habit_boost": True,
        }

    return body, out
