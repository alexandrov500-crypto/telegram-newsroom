from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.self_audit import build_self_audit_bullets
from bot.editorial.flow_health.state import load_state


def build_operational_drift_narratives() -> list[str]:
    """Heuristic week-over-week narratives — no AI summarization."""
    st = load_state()
    audits: dict[str, Any] = dict(st.get("weekly_audits") or {})
    if len(audits) < 2:
        return ["Operational drift: establishing weekly narrative baseline"]

    keys = sorted(audits.keys())
    prev, cur = audits[keys[-2]], audits[keys[-1]]
    narratives: list[str] = []

    ch = float(cur.get("vitality_score") or 0) - float(prev.get("vitality_score") or 0)
    if abs(ch) >= 0.05:
        if ch < 0:
            narratives.append("Cadence stable, vitality declining" if ch < -0.08 else "Vitality softening")
        else:
            narratives.append("Editorial vitality improving")

    tr = float(cur.get("trust_index") or 0) - float(prev.get("trust_index") or 0)
    if tr > 0.05:
        narratives.append("Operator trust trending up")
    elif tr < -0.05:
        narratives.append("Trust erosion over the week")

    if prev.get("degradation_mode") != cur.get("degradation_mode"):
        if cur.get("degradation_mode") == "NORMAL":
            narratives.append("Degradation modes normalized")
        else:
            narratives.append("Recovery oscillation increased slightly")

    inf_p = int(prev.get("influence_count") or 0)
    inf_c = int(cur.get("influence_count") or 0)
    if inf_c < inf_p - 1:
        narratives.append("Heuristic coupling reduced — configuration churn stabilized")
    elif inf_c > inf_p + 1:
        narratives.append("Adaptive coupling increased — review tuning")

    if not narratives:
        narratives.append("Long-run operation stable — no major drift narrative")

    bullets = build_self_audit_bullets()
    return (narratives + bullets)[:6]
