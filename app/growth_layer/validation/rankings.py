"""Top content rankings using proxy acquisition metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.growth_layer.validation.acquisition_proxy import acquisition_proxy_score
from app.growth_layer.validation.status import filter_final_rows


@dataclass(frozen=True)
class GrowthRankings:
    top_subscriber_drivers: tuple[dict[str, Any], ...] = ()
    top_forward_drivers: tuple[dict[str, Any], ...] = ()
    top_err_drivers: tuple[dict[str, Any], ...] = ()
    top_engagement: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_subscriber_drivers": list(self.top_subscriber_drivers),
            "top_forward_drivers": list(self.top_forward_drivers),
            "top_err_drivers": list(self.top_err_drivers),
            "top_engagement": list(self.top_engagement),
        }


def _rank(rows: list[dict[str, Any]], key_fn, *, limit: int = 10) -> tuple[dict[str, Any], ...]:
    scored = [(key_fn(r), r) for r in rows]
    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, Any]] = []
    for score, row in scored[:limit]:
        item = dict(row)
        item["rank_score"] = round(score, 4)
        out.append(item)
    return tuple(out)


def build_growth_rankings(rows: list[dict[str, Any]], *, limit: int = 10, final_only: bool = True) -> GrowthRankings:
    pool = filter_final_rows(rows) if final_only else rows
    usable = [r for r in pool if r.get("actual_engagement") is not None and int(r.get("actual_views") or 0) >= 20]
    return GrowthRankings(
        top_subscriber_drivers=_rank(usable, acquisition_proxy_score, limit=limit),
        top_forward_drivers=_rank(usable, lambda r: float(r.get("actual_forwards") or 0), limit=limit),
        top_err_drivers=_rank(usable, lambda r: float(r.get("actual_err") or 0), limit=limit),
        top_engagement=_rank(usable, lambda r: float(r.get("actual_engagement") or 0), limit=limit),
    )
