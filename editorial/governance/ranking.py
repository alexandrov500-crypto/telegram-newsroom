"""Deterministic weighted editorial ranking with explicit scoring trace."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Sequence

from db.models import RawPost

from editorial.diversity import compute_diversity_signals
from editorial.governance.operator_controls import operator_adjustments_for_cluster
from editorial.governance.paths import ranking_snapshot_path, ranking_weights_path
from editorial.governance.reputation import explainable_reputation
from editorial.intelligence_store import load_json, save_json
from scheduler.precluster import avg_pairwise_lexical_cohesion

DEFAULT_WEIGHTS: dict[str, float] = {
    "freshness": 0.20,
    "source_reputation": 0.18,
    "novelty": 0.15,
    "topic_diversity": 0.12,
    "engagement": 0.10,
    "duplicate_suppression": 0.15,
    "operator_boost": 0.10,
}


@dataclass(slots=True)
class RankingTrace:
    fingerprint: str
    topic_hint: str
    stages: dict[str, float]
    weights: dict[str, float]
    weighted_total: float
    tie_break: tuple[Any, ...]
    reason_codes: list[str] = field(default_factory=list)
    hard_block: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "topic_hint": self.topic_hint,
            "stages": dict(self.stages),
            "weights": dict(self.weights),
            "weighted_total": self.weighted_total,
            "tie_break": list(self.tie_break),
            "reason_codes": list(self.reason_codes),
            "hard_block": self.hard_block,
        }


def load_ranking_weights(runtime_dir: str | None) -> dict[str, float]:
    raw = load_json(ranking_weights_path(runtime_dir), {"weights": DEFAULT_WEIGHTS})
    w = raw.get("weights") if isinstance(raw.get("weights"), dict) else raw
    out = dict(DEFAULT_WEIGHTS)
    if isinstance(w, dict):
        for k, v in w.items():
            if k in DEFAULT_WEIGHTS:
                try:
                    out[k] = float(v)
                except (TypeError, ValueError):
                    pass
    return out


def _freshness_score(posts: Sequence[RawPost]) -> float:
    if not posts:
        return 0.0
    newest = max(int(p.created_at.timestamp()) for p in posts)
    age_h = max(0.0, (time.time() - newest) / 3600.0)
    return round(max(0.05, 1.0 - min(1.0, age_h / 48.0)), 4)


def _novelty_score(evolution_kind: str) -> float:
    k = str(evolution_kind or "").lower()
    if k in ("new", "breaking", "emerging"):
        return 0.95
    if k in ("developing", "update"):
        return 0.72
    if k in ("repeat", "duplicate"):
        return 0.25
    return 0.55


def _engagement_score(posts: Sequence[RawPost], cohesion: float) -> float:
    n = len(posts)
    size = min(1.0, n / 8.0)
    return round(0.55 * size + 0.45 * cohesion, 4)


def score_cluster_candidate(
    posts: list[RawPost],
    *,
    runtime_dir: str | None,
    fingerprint: str,
    topic_hint: str,
    evolution_kind: str = "new",
    duplicate_similarity_pct: float = 0.0,
    entity_norms: Sequence[str] | None = None,
    weights_override: dict[str, float] | None = None,
) -> RankingTrace:
    weights = weights_override if weights_override is not None else load_ranking_weights(runtime_dir)
    rep_map = explainable_reputation(runtime_dir)
    chans = [str(p.channel_name or "").strip().lower() for p in posts if str(p.channel_name or "").strip()]
    rep_vals = [float(rep_map.get(c, {}).get("score") or 0.5) for c in chans] or [0.5]
    rep_score = round(sum(rep_vals) / len(rep_vals), 4)
    div = compute_diversity_signals(posts, topic_hint, tuple(entity_norms or ()))
    diversity_score = round(
        0.45 * div.unique_channel_ratio + 0.35 * (1.0 - div.channel_concentration) + 0.2 * (1.0 - div.entity_token_repetition),
        4,
    )
    cohesion = avg_pairwise_lexical_cohesion(list(posts))
    dup_pen = round(min(1.0, duplicate_similarity_pct / 100.0), 4)
    op_delta, op_codes, hard = operator_adjustments_for_cluster(
        runtime_dir, channels=chans, topic_key=topic_hint
    )
    stages = {
        "freshness": _freshness_score(posts),
        "source_reputation": rep_score,
        "novelty": _novelty_score(evolution_kind),
        "topic_diversity": diversity_score,
        "engagement": _engagement_score(posts, cohesion),
        "duplicate_suppression": -dup_pen,
        "operator_boost": op_delta,
    }
    total = 0.0
    for key, w in weights.items():
        total += float(stages.get(key, 0.0)) * float(w)
    total = round(total, 6)
    if hard:
        total = -1.0
    newest_id = max((int(p.id) for p in posts), default=0)
    tie = (-total, -newest_id, -len(posts), str(fingerprint))
    codes: list[str] = []
    if stages["freshness"] >= 0.8:
        codes.append("high_freshness")
    if rep_score >= 0.7:
        codes.append("trusted_sources")
    if dup_pen >= 0.55:
        codes.append("duplicate_risk_elevated")
    codes.extend(op_codes)
    return RankingTrace(
        fingerprint=fingerprint,
        topic_hint=topic_hint,
        stages=stages,
        weights=weights,
        weighted_total=total,
        tie_break=tie,
        reason_codes=codes,
        hard_block=hard,
    )


def rank_clusters(
    candidates: list[dict[str, Any]],
    *,
    runtime_dir: str | None,
    weights_override: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Rank cluster dicts with keys: posts, fingerprint, topic_hint, evolution_kind, duplicate_similarity_pct."""
    traces: list[tuple[RankingTrace, dict[str, Any]]] = []
    for cand in candidates:
        posts = list(cand.get("posts") or [])
        if not posts:
            continue
        tr = score_cluster_candidate(
            posts,
            runtime_dir=runtime_dir,
            fingerprint=str(cand.get("fingerprint") or ""),
            topic_hint=str(cand.get("topic_hint") or ""),
            evolution_kind=str(cand.get("evolution_kind") or "new"),
            duplicate_similarity_pct=float(cand.get("duplicate_similarity_pct") or 0.0),
            entity_norms=cand.get("entity_norms"),
            weights_override=weights_override,
        )
        traces.append((tr, cand))
    traces.sort(key=lambda x: x[0].tie_break)
    ranked: list[dict[str, Any]] = []
    for i, (tr, cand) in enumerate(traces):
        ranked.append({
            "rank": i + 1,
            "fingerprint": tr.fingerprint,
            "topic_hint": tr.topic_hint,
            "trace": tr.to_dict(),
            "cluster_size": len(cand.get("posts") or []),
        })
    snapshot = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "weights": load_ranking_weights(runtime_dir),
        "candidates": len(ranked),
        "ranked": ranked[:50],
    }
    save_json(ranking_snapshot_path(runtime_dir), snapshot)
    return ranked


def get_last_ranking_snapshot(runtime_dir: str | None) -> dict[str, Any]:
    return load_json(
        ranking_snapshot_path(runtime_dir),
        {"ts": None, "weights": load_ranking_weights(runtime_dir), "candidates": 0, "ranked": []},
    )
