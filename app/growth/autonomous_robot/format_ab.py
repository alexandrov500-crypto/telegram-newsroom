"""
Format A/B — subscriber_wire vs cb_brief with automatic winner lock.

Primary metric: forward rate (t24h). Secondary: engagement, acquisition proxy.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import md5
from pathlib import Path
from typing import Any

from app.growth_layer.statistics.effect_size import calculate_effect_size, effect_size_meets_minimum
from app.growth_layer.statistics.significance import compare_two_samples
from app.growth_layer.validation.acquisition_proxy import acquisition_proxy_score
from app.growth_layer.validation.status import filter_final_rows

_STATE_FILE = "autonomous_format_ab.json"
_VARIANTS = ("subscriber_wire", "cb_brief")


def format_ab_experiment_enabled() -> bool:
    if os.getenv("FORMAT_AB_EXPERIMENT_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return False
    from app.growth_layer.format.profiles import publish_format_mode

    return publish_format_mode() == "format_ab"


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / _STATE_FILE


def load_format_ab_state(runtime_dir: str) -> dict[str, Any]:
    try:
        data = json.loads(_state_path(runtime_dir).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_format_ab_state(runtime_dir: str, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(UTC).isoformat()
    path = _state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _wire_share() -> float:
    try:
        return max(0.2, min(0.8, float(os.getenv("FORMAT_AB_WIRE_SHARE", "0.5"))))
    except ValueError:
        return 0.5


def assign_format_variant(*, draft_id: int, content: str = "") -> str:
    """Stable per-draft assignment while experiment is active."""
    runtime_dir = os.getenv("RUNTIME_STATE_DIR", "./var/runtime").strip()
    state = load_format_ab_state(runtime_dir)
    if state.get("winner_locked") and state.get("winner") in _VARIANTS:
        return str(state["winner"])

    key = f"{draft_id}:{(content or '')[:64]}"
    bucket = int(md5(key.encode("utf-8")).hexdigest(), 16) % 100
    share = float(state.get("wire_share") or _wire_share())
    return "subscriber_wire" if bucket < int(share * 100) else "cb_brief"


def apply_format_ab_env_overrides(runtime_dir: str | None = None) -> dict[str, str]:
    """If winner locked, force NEWSROOM_PUBLISH_FORMAT to winner."""
    rd = runtime_dir or os.getenv("RUNTIME_STATE_DIR", "./var/runtime").strip()
    state = load_format_ab_state(rd)
    applied: dict[str, str] = {}
    if state.get("winner_locked") and state.get("winner") in _VARIANTS:
        winner = str(state["winner"])
        os.environ["NEWSROOM_PUBLISH_FORMAT"] = winner
        applied["NEWSROOM_PUBLISH_FORMAT"] = winner
    elif format_ab_experiment_enabled() or os.getenv("NEWSROOM_PUBLISH_FORMAT", "").strip().lower() == "format_ab":
        os.environ["NEWSROOM_PUBLISH_FORMAT"] = "format_ab"
        applied["NEWSROOM_PUBLISH_FORMAT"] = "format_ab"
    return applied


def _min_cohort() -> int:
    try:
        return max(8, int(os.getenv("FORMAT_AB_MIN_COHORT", "15")))
    except ValueError:
        return 15


def _min_total() -> int:
    try:
        return max(16, int(os.getenv("FORMAT_AB_MIN_TOTAL", "30")))
    except ValueError:
        return 30


def _forward_lift_min() -> float:
    try:
        return float(os.getenv("FORMAT_AB_FORWARD_LIFT_MIN", "8.0"))
    except ValueError:
        return 8.0


def _alpha() -> float:
    try:
        return float(os.getenv("FORMAT_AB_SIGNIFICANCE_ALPHA", "0.08"))
    except ValueError:
        return 0.08


def _metric_values(rows: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for r in rows:
        if key == "acquisition_proxy_score":
            out.append(float(acquisition_proxy_score(r)))
        elif r.get(key) is not None:
            out.append(float(r[key]))
    return out


@dataclass(frozen=True)
class FormatAbVerdict:
    winner: str | None
    meets_threshold: bool
    reason: str
    wire_sample: int
    cb_sample: int
    wire_mean_forward: float | None
    cb_mean_forward: float | None
    forward_lift_pct: float | None
    forward_p_value: float | None
    effect_size: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "meets_threshold": self.meets_threshold,
            "reason": self.reason,
            "wire_sample": self.wire_sample,
            "cb_sample": self.cb_sample,
            "wire_mean_forward": self.wire_mean_forward,
            "cb_mean_forward": self.cb_mean_forward,
            "forward_lift_pct": self.forward_lift_pct,
            "forward_p_value": self.forward_p_value,
            "effect_size": self.effect_size,
        }


def evaluate_wire_vs_cb(rows: list[dict[str, Any]], *, final_only: bool = True) -> FormatAbVerdict:
    validated = filter_final_rows(rows) if final_only else rows
    wire = [r for r in validated if str(r.get("format_profile") or "") == "subscriber_wire"]
    cb = [r for r in validated if str(r.get("format_profile") or "") == "cb_brief"]

    min_cohort = _min_cohort()
    min_total = _min_total()
    sample_size = len(validated)

    w_fr = _metric_values(wire, "actual_forward_rate")
    c_fr = _metric_values(cb, "actual_forward_rate")
    w_mean = sum(w_fr) / len(w_fr) if w_fr else None
    c_mean = sum(c_fr) / len(c_fr) if c_fr else None

    if sample_size < min_total or len(wire) < min_cohort or len(cb) < min_cohort:
        return FormatAbVerdict(
            winner=None,
            meets_threshold=False,
            reason="insufficient_samples",
            wire_sample=len(wire),
            cb_sample=len(cb),
            wire_mean_forward=round(w_mean, 5) if w_mean is not None else None,
            cb_mean_forward=round(c_mean, 5) if c_mean is not None else None,
            forward_lift_pct=None,
            forward_p_value=None,
            effect_size="unknown",
        )

    if w_mean is None or c_mean is None:
        return FormatAbVerdict(
            winner=None,
            meets_threshold=False,
            reason="missing_forward_metrics",
            wire_sample=len(wire),
            cb_sample=len(cb),
            wire_mean_forward=None,
            cb_mean_forward=None,
            forward_lift_pct=None,
            forward_p_value=None,
            effect_size="unknown",
        )

    if w_mean >= c_mean:
        winner_candidate = "subscriber_wire"
        treatment, control = w_fr, c_fr
        lift = ((w_mean - c_mean) / max(c_mean, 1e-9)) * 100.0
    else:
        winner_candidate = "cb_brief"
        treatment, control = c_fr, w_fr
        lift = ((c_mean - w_mean) / max(w_mean, 1e-9)) * 100.0

    sig = compare_two_samples(treatment, control, alternative="greater")
    effect = calculate_effect_size(treatment, control)
    p_val = sig.get("p_value")
    effect_label = str(effect.get("classification") or "unknown")
    alpha = _alpha()

    meets = (
        lift >= _forward_lift_min()
        and p_val is not None
        and float(p_val) < alpha
        and effect_size_meets_minimum(effect_label)
    )

    return FormatAbVerdict(
        winner=winner_candidate if meets else None,
        meets_threshold=bool(meets),
        reason="forward_rate_winner" if meets else "not_significant",
        wire_sample=len(wire),
        cb_sample=len(cb),
        wire_mean_forward=round(w_mean, 5),
        cb_mean_forward=round(c_mean, 5),
        forward_lift_pct=round(lift, 2),
        forward_p_value=round(float(p_val), 5) if p_val is not None else None,
        effect_size=effect_label,
    )


def lock_format_winner(runtime_dir: str, winner: str, verdict: FormatAbVerdict) -> dict[str, Any]:
    state = load_format_ab_state(runtime_dir)
    state.update(
        {
            "winner_locked": True,
            "winner": winner,
            "locked_at": datetime.now(UTC).isoformat(),
            "verdict": verdict.to_dict(),
            "experiment_active": False,
        }
    )
    save_format_ab_state(runtime_dir, state)
    apply_format_ab_env_overrides(runtime_dir)
    return state


def init_format_ab_state(runtime_dir: str) -> dict[str, Any]:
    state = load_format_ab_state(runtime_dir)
    if state.get("winner_locked"):
        return state
    if not state:
        state = {
            "experiment_active": True,
            "winner_locked": False,
            "winner": None,
            "wire_share": _wire_share(),
            "variants": list(_VARIANTS),
            "primary_metric": "actual_forward_rate",
        }
        save_format_ab_state(runtime_dir, state)
    return state


async def run_format_ab_evaluation(runtime_dir: str) -> dict[str, Any]:
    if not format_ab_experiment_enabled():
        state = load_format_ab_state(runtime_dir)
        if state.get("winner_locked"):
            return {"skipped": "winner_locked", "winner": state.get("winner")}
        return {"skipped": "experiment_disabled"}

    init_format_ab_state(runtime_dir)
    state = load_format_ab_state(runtime_dir)
    if state.get("winner_locked"):
        return {"skipped": "winner_locked", "winner": state.get("winner")}

    from db.growth_validation_repository import list_post_growth_validation
    from db.session import session_scope

    async with session_scope() as session:
        rows = await list_post_growth_validation(session, limit=400, since_days=90, final_only=True)

    verdict = evaluate_wire_vs_cb(rows)
    result: dict[str, Any] = {"verdict": verdict.to_dict()}

    if verdict.meets_threshold and verdict.winner:
        result["state"] = lock_format_winner(runtime_dir, verdict.winner, verdict)
        result["applied"] = True
    else:
        result["applied"] = False

    snapshot_path = Path(runtime_dir) / "format_ab_latest.json"
    snapshot_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def format_ab_status_text(runtime_dir: str) -> str:
    state = load_format_ab_state(runtime_dir)
    if state.get("winner_locked"):
        v = (state.get("verdict") or {}) if isinstance(state.get("verdict"), dict) else {}
        return (
            f"🔒 Format A/B locked → {state.get('winner')}\n"
            f"forward lift {v.get('forward_lift_pct')}% · p={v.get('forward_p_value')}"
        )
    latest: dict[str, Any] = {}
    try:
        latest = json.loads((Path(runtime_dir) / "format_ab_latest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    verdict = latest.get("verdict") if isinstance(latest.get("verdict"), dict) else {}
    return (
        f"🧪 Format A/B running (wire {int(float(state.get('wire_share') or _wire_share()) * 100)}%)\n"
        f"samples wire={verdict.get('wire_sample', '?')} cb={verdict.get('cb_sample', '?')} · "
        f"forward wire={verdict.get('wire_mean_forward', '?')} cb={verdict.get('cb_mean_forward', '?')}"
    )
