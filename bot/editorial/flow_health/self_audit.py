from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def record_weekly_audit_snapshot(
    *,
    trust_index: float | None,
    realism_index: float | None,
    vitality_score: float | None,
    degradation_mode: str,
    simplicity_index: float | None,
    influence_count: int,
) -> None:
    week = datetime.now(timezone.utc).strftime("%Y-W%W")
    st = load_state()
    audits: dict[str, Any] = dict(st.get("weekly_audits") or {})
    audits[week] = {
        "trust_index": trust_index,
        "realism_index": realism_index,
        "vitality_score": vitality_score,
        "degradation_mode": degradation_mode,
        "simplicity_index": simplicity_index,
        "influence_count": influence_count,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    keys = sorted(audits.keys())[-8:]
    audits = {k: audits[k] for k in keys}
    try:
        save_state(metrics={"weekly_audits": audits})
    except Exception:
        pass


def build_self_audit_bullets() -> list[str]:
    """What changed over the last week — compressed digest bullets."""
    st = load_state()
    audits: dict[str, Any] = dict(st.get("weekly_audits") or {})
    if len(audits) < 2:
        return ["Self-audit: accumulating weekly baseline (need 2+ weeks)"]

    keys = sorted(audits.keys())
    prev, cur = audits[keys[-2]], audits[keys[-1]]
    bullets: list[str] = []

    def _delta(key: str, label: str, fmt: str = ".2f") -> None:
        a, b = prev.get(key), cur.get(key)
        if a is None or b is None:
            return
        d = float(b) - float(a)
        if abs(d) >= 0.04:
            bullets.append(f"{label} {'↑' if d > 0 else '↓'} ({float(a):{fmt}} → {float(b):{fmt}})")

    _delta("realism_index", "Realism")
    _delta("vitality_score", "Vitality")
    _delta("trust_index", "Trust")
    _delta("simplicity_index", "Simplicity")

    if prev.get("degradation_mode") != cur.get("degradation_mode"):
        bullets.append(
            f"Degradation mode {prev.get('degradation_mode')} → {cur.get('degradation_mode')}",
        )

    inf_a = int(prev.get("influence_count") or 0)
    inf_b = int(cur.get("influence_count") or 0)
    if abs(inf_b - inf_a) >= 2:
        bullets.append(f"Active heuristic count {inf_a} → {inf_b}")

    if not bullets:
        bullets.append("No material weekly shifts detected")
    return bullets[:5]
