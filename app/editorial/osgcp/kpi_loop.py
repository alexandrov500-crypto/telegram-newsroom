"""Real-time editorial KPI loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.stability.slo import stability_slo_snapshot


@dataclass(frozen=True)
class EditorialKPIState:
    continuity_gap_max: float | None
    posts_per_day_actual: int
    gravity_avg_rolling: float
    substitution_rate: float
    forward_rate: float | None
    save_rate: float | None
    return_within_24h: float | None
    pct_synthesis: float
    pct_priority_boost: float
    pct_rejected: float
    pct_digest: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "continuity_gap_max": self.continuity_gap_max,
            "posts_per_day_actual": self.posts_per_day_actual,
            "gravity_avg_rolling": round(self.gravity_avg_rolling, 2),
            "substitution_rate": round(self.substitution_rate, 2),
            "forward_rate": self.forward_rate,
            "save_rate": self.save_rate,
            "return_within_24h": self.return_within_24h,
            "pct_synthesis": round(self.pct_synthesis, 1),
            "pct_priority_boost": round(self.pct_priority_boost, 1),
            "pct_rejected": round(self.pct_rejected, 1),
            "pct_digest": round(self.pct_digest, 1),
        }


def compute_editorial_kpi_state(runtime_dir: str | None = None) -> EditorialKPIState:
    from app.editorial.growth_dominance.state import today_gravity_stats
    from app.editorial.osgcp.state import load_state
    from app.editorial.product_os.state import load_state as load_peos

    slo = stability_slo_snapshot(runtime_dir)
    grav = today_gravity_stats(runtime_dir)

    day_peos = {}
    day_osgcp = {}
    try:
        import time

        day_key = time.strftime("%Y-%m-%d", time.gmtime())
        day_peos = dict((load_peos(runtime_dir).get("days") or {}).get(day_key) or {})
        day_osgcp = dict((load_state(runtime_dir).get("days") or {}).get(day_key) or {})
    except Exception:
        pass

    evaluated = max(1, int(day_osgcp.get("evaluated") or 0))
    subs = [float(x) for x in (day_peos.get("substitution_scores") or [])]
    sub_avg = sum(subs) / len(subs) if subs else 0.0

    action_counts = dict(day_osgcp.get("action_counts") or {})
    total_actions = sum(int(v) for v in action_counts.values()) or evaluated

    def _pct(key: str) -> float:
        return round(int(action_counts.get(key) or 0) / total_actions * 100.0, 1)

    gap_info = slo.get("slo") or {}
    posts_today = int((slo.get("posts_today") or grav.get("posts_published") or 0))

    return EditorialKPIState(
        continuity_gap_max=gap_info.get("publish_gap_minutes"),
        posts_per_day_actual=posts_today,
        gravity_avg_rolling=float(grav.get("avg_gravity") or 0),
        substitution_rate=sub_avg,
        forward_rate=None,
        save_rate=None,
        return_within_24h=None,
        pct_synthesis=_pct("synthesize"),
        pct_priority_boost=_pct("priority_boost"),
        pct_rejected=_pct("reject"),
        pct_digest=_pct("digest"),
    )
