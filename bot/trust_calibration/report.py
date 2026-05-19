from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.trust_calibration.agreement import analyze_operator_agreement
from bot.trust_calibration.profiles import operator_trust_profile
from bot.trust_calibration.repository import TrustCalibrationRepository
from bot.trust_calibration.stability import score_confidence_drift
from bot.trust_calibration.subsystems import compute_subsystem_metrics, detect_reliability_decay
from bot.trust_calibration.types import TrustBand
from bot.storage.db import init_database


def build_trust_calibration(db_path: Path) -> dict[str, Any]:
    path = init_database(db_path)
    repo = TrustCalibrationRepository(path)
    events = repo.events_since(hours=168)
    ratings = repo.ratings_with_traces(limit=150)
    agreement = analyze_operator_agreement(ratings)
    subsystems = compute_subsystem_metrics(events, agreement)
    drift = score_confidence_drift(path)
    profile = operator_trust_profile(events)
    historical = repo.load_subsystem_daily(days=14)
    decay_alerts = detect_reliability_decay(subsystems, historical)

    day = datetime.now(timezone.utc).date().isoformat()
    for sub, metrics in subsystems.items():
        repo.save_subsystem_daily(day, sub, metrics, metrics["trust_band"])

    longitudinal = _longitudinal_trend(repo, subsystems)
    snapshot = {
        "date": day,
        "agreement": agreement,
        "subsystems": subsystems,
        "confidence_drift": drift,
        "operator_profile": profile,
        "decay_alerts": decay_alerts,
        "longitudinal": longitudinal,
        "guidance": _guidance_text(subsystems),
    }
    repo.save_calibration_daily(day, snapshot)
    return snapshot


def _longitudinal_trend(
    repo: TrustCalibrationRepository,
    current: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    history = repo.load_subsystem_daily(days=14)
    if not history:
        return {"direction": "insufficient_data", "avg_reliability": None}
    scores = [
        float((row.get("metrics") or {}).get("reliability") or 0)
        for row in history
    ]
    avg = sum(scores) / len(scores) if scores else 0.5
    cur_avg = sum(float(m.get("reliability") or 0) for m in current.values()) / max(
        1,
        len(current),
    )
    direction = "stable"
    if cur_avg > avg + 0.05:
        direction = "improving"
    elif cur_avg < avg - 0.05:
        direction = "degrading"
    return {"direction": direction, "avg_reliability": round(avg, 3), "current_avg": round(cur_avg, 3)}


def _guidance_text(subsystems: dict[str, dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for sub, m in subsystems.items():
        band = m.get("trust_band", TrustBand.EXPERIMENTAL.value)
        if band == TrustBand.HIGHLY_RELIABLE.value:
            lines.append(f"{sub}: treat as primary signal")
        elif band == TrustBand.STABLE.value:
            lines.append(f"{sub}: useful with routine review")
        elif band == TrustBand.EXPERIMENTAL.value:
            lines.append(f"{sub}: advisory only — confirm manually")
        else:
            lines.append(f"{sub}: low confidence — human judgment required")
    return lines


def build_trust_calibration_html(snapshot: dict[str, Any]) -> str:
    agree = snapshot.get("agreement", {}).get("totals", {})
    drift = snapshot.get("confidence_drift") or {}
    longi = snapshot.get("longitudinal") or {}
    lines = [
        "<b>Trust calibration</b>",
        "<i>Subsystem reliability — advisory only</i>",
        "",
        "<b>Operator agreement</b>",
        f"Rated: {agree.get('rated', 0)} · good {agree.get('good', 0)} · bad {agree.get('bad', 0)}",
        f"Priority agree/disagree: {agree.get('priority_high_agree', 0)}/"
        f"{agree.get('priority_high_disagree', 0)}",
        f"Warnings confirmed: {agree.get('warning_confirmed', 0)} · "
        f"false positive: {agree.get('warning_false_positive', 0)} · "
        f"missed: {agree.get('warning_ignored_then_bad', 0)}",
        "",
        f"<b>Confidence drift</b>: <code>{html.escape(str(drift.get('drift_alert', 'stable')))}</code>",
        f"Longitudinal: <code>{html.escape(str(longi.get('direction', '?')))}</code> "
        f"(avg rel {longi.get('avg_reliability', '—')})",
        "",
        "<b>Subsystem bands</b>",
    ]
    for sub, m in (snapshot.get("subsystems") or {}).items():
        lines.append(
            f"• <code>{html.escape(sub)}</code> "
            f"[{html.escape(str(m.get('trust_band', '?')))}] "
            f"rel {m.get('reliability', 0):.2f} · prec {m.get('precision', 0):.2f} · "
            f"stab {m.get('stability', 0):.2f}",
        )
    decay = snapshot.get("decay_alerts") or []
    if decay:
        lines.append("")
        lines.append("<b>Reliability decay</b>")
        for d in decay[:4]:
            lines.append(f"⚠ {html.escape(d.get('message', '')[:100])}")
    guidance = snapshot.get("guidance") or []
    if guidance:
        lines.append("")
        lines.append("<b>Guidance</b>")
        for g in guidance[:7]:
            lines.append(f"• {html.escape(g)}")
    return "\n".join(lines)
