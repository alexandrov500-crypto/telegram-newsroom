from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bot.ops_evidence.confidence import compute_operational_confidence
from bot.ops_evidence.incidents import discover_incident_patterns
from bot.ops_evidence.noise import detect_retirement_candidates
from bot.ops_evidence.repository import EvidenceReviewRepository
from bot.ops_evidence.runtime_summary import (
    build_runtime_weekly_summary,
    week_db_publish_stats,
)
from bot.ops_evidence.signals import rank_signal_effectiveness
from bot.ops_evidence.timeline import build_reliability_timeline
from bot.ops_evidence.tuning import generate_tuning_suggestions
from bot.ops_evidence.workflow import analyze_operator_workflow
from bot.ops_observation.store import OpsObservationStore
from bot.operator_ux.repository import AttentionMetricsRepository
from bot.ops_forensics.repository import ForensicsRepository
from bot.storage.db import init_database
from bot.trust_calibration.agreement import analyze_operator_agreement
from bot.trust_calibration.repository import TrustCalibrationRepository
from bot.trust_calibration.report import build_trust_calibration


def week_id_for(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(timezone.utc)
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def build_weekly_operational_review(
    db_path: Path,
    *,
    hours: int = 168,
    base_url: str = "http://127.0.0.1:8080",
    persist: bool = True,
) -> dict[str, Any]:
    path = init_database(db_path)
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

    store = OpsObservationStore()
    runtime = build_runtime_weekly_summary(store=store)
    publish_stats = week_db_publish_stats(path, hours=hours)

    trust_repo = TrustCalibrationRepository(path)
    trust = build_trust_calibration(path)
    ratings = trust_repo.ratings_with_traces(limit=200)
    agreement = analyze_operator_agreement(ratings)
    events = trust_repo.events_since(hours=hours)

    signal_rankings = rank_signal_effectiveness(events, agreement)
    subsystems = trust.get("subsystems") or {}
    historical = trust_repo.load_subsystem_daily(days=30)
    reliability_timeline = build_reliability_timeline(historical)

    attention_repo = AttentionMetricsRepository(path)
    noise_metrics = attention_repo.noise_metrics(hours=hours)

    retirement_candidates = detect_retirement_candidates(
        signal_rankings,
        subsystems,
        noise_metrics,
    )

    forensics = ForensicsRepository(path)
    timeline_events = forensics.query_timeline(since=since, limit=800)
    audit_rows = forensics.query_audit(limit=500)
    incident_patterns = discover_incident_patterns(timeline_events)

    workflow = analyze_operator_workflow(audit_rows, hours=hours)

    storylines: list[dict[str, Any]] = []
    editorial_week: dict[str, Any] = {}
    fatigue_hotspots: list[str] = []
    try:
        from bot.editorial.memory.service import get_editorial_memory_repo

        mem = get_editorial_memory_repo(path)
        raw_storylines = mem.active_storylines(limit=8) or []
        storylines = [
            {
                "storyline_id": s.storyline_id,
                "title": s.title,
                "publish_count": s.publish_count,
                "saturation": s.saturation_score,
            }
            for s in raw_storylines
        ]
    except Exception:
        pass

    try:
        from bot.editorial.quality.repository import EditorialQualityRepository

        eq = EditorialQualityRepository(path)
        snaps = eq.load_daily_snapshots(limit=7)
        scores = [float(s.get("avg_editorial_quality_score") or 0) for s in snaps if s]
        editorial_week = {
            "daily_snapshots": len(snaps),
            "avg_quality_score": round(sum(scores) / len(scores), 3) if scores else None,
        }
        for s in snaps:
            for w in (s.get("top_warnings") or [])[:3]:
                if "fatigue" in str(w).lower():
                    fatigue_hotspots.append(str(w))
    except Exception:
        pass

    confidence = compute_operational_confidence(
        runtime=runtime,
        publish_stats=publish_stats,
        trust_snapshot=trust,
        agreement=agreement,
        incident_count=len(publish_stats.get("incidents") or []),
        timeline_direction=str(reliability_timeline.get("direction") or "stable"),
    )

    tuning = generate_tuning_suggestions(
        subsystems=subsystems,
        signal_rankings=signal_rankings,
        retirement_candidates=retirement_candidates,
        runtime=runtime,
        incident_patterns=incident_patterns,
    )

    noisy_alerts = [c for c in retirement_candidates if "suppression" in c.get("label", "")]
    ignored_warnings = [
        r for r in signal_rankings if float(r.get("ignore_ratio") or 0) >= 0.5
    ][:10]

    wid = week_id_for()
    review = {
        "week_id": wid,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_hours": hours,
        "operational_confidence": confidence,
        "runtime": runtime,
        "publish_trends": publish_stats,
        "trust_calibration": {
            "longitudinal": trust.get("longitudinal"),
            "decay_alerts": trust.get("decay_alerts"),
            "subsystems": subsystems,
            "agreement": agreement,
        },
        "signal_effectiveness": signal_rankings[:20],
        "retirement_candidates": retirement_candidates,
        "reliability_timeline": reliability_timeline,
        "operator_workflow": workflow,
        "incident_patterns": incident_patterns,
        "tuning_suggestions": tuning,
        "editorial_week": editorial_week,
        "top_storylines": storylines[:8],
        "fatigue_hotspots": list(dict.fromkeys(fatigue_hotspots))[:8],
        "noisy_alerts": noisy_alerts,
        "ignored_warnings": ignored_warnings,
        "recurring_incidents": publish_stats.get("incidents") or [],
        "attention_noise": noise_metrics,
    }

    if persist:
        try:
            EvidenceReviewRepository(path).save_review(
                week_id=wid,
                snapshot=review,
                confidence_band=confidence["band"],
                confidence_score=float(confidence["score"]),
            )
        except Exception:
            pass

    return review


def build_weekly_review_html(snapshot: dict[str, Any]) -> str:
    conf = snapshot.get("operational_confidence") or {}
    runtime = snapshot.get("runtime") or {}
    pulse = runtime.get("pulse") or {}
    pub = snapshot.get("publish_trends") or {}
    trust = snapshot.get("trust_calibration") or {}
    agree = trust.get("agreement", {}).get("totals", {})
    timeline = snapshot.get("reliability_timeline") or {}
    workflow = snapshot.get("operator_workflow") or {}

    lines = [
        f"<b>Weekly operational review</b> · {html.escape(str(snapshot.get('week_id', '?')))}",
        f"<i>{html.escape(str(snapshot.get('generated_at', ''))[:19])} UTC</i>",
        "",
        "<b>Operational confidence</b>",
        f"Band: <code>{html.escape(str(conf.get('band', '?')))}</code> · "
        f"score {float(conf.get('score') or 0):.2f}",
        f"Evolution: <code>{html.escape(str(timeline.get('direction', '?')))}</code>",
        "",
        "<b>Runtime (7d)</b>",
        f"Pulses: {pulse.get('pulse_count', 0)} · lag max {float(pulse.get('event_loop_lag_max') or 0):.3f}s · "
        f"stalled {pulse.get('stalled_loop_events', 0)}",
        f"Publish success: {pub.get('success_rate', '—')} · published {pub.get('published', 0)}",
        "",
        "<b>Operator agreement</b>",
        f"Rated: {agree.get('rated', 0)} · confirmed warnings {agree.get('warning_confirmed', 0)} · "
        f"false positives {agree.get('warning_false_positive', 0)}",
    ]

    decay = trust.get("decay_alerts") or []
    if decay:
        lines.append("")
        lines.append("<b>Trust decay alerts</b>")
        for d in decay[:4]:
            lines.append(f"• {html.escape(str(d.get('message', d)))}")

    lines.extend(["", "<b>Top signals (usefulness)</b>"])
    for row in (snapshot.get("signal_effectiveness") or [])[:6]:
        lines.append(
            f"• <code>{html.escape(str(row.get('signal', '?')))}</code> "
            f"score {float(row.get('usefulness_score') or 0):.2f} · "
            f"prec {float(row.get('precision') or 0):.0%}",
        )

    candidates = snapshot.get("retirement_candidates") or []
    if candidates:
        lines.extend(["", "<b>Noise / retirement candidates (advisory)</b>"])
        for c in candidates[:5]:
            lines.append(
                f"• [{html.escape(str(c.get('label', '?')))}] "
                f"{html.escape(str(c.get('signal', '?')))}",
            )

    suggestions = snapshot.get("tuning_suggestions") or []
    if suggestions:
        lines.extend(["", "<b>Tuning suggestions (human decides)</b>"])
        for s in suggestions[:6]:
            lines.append(f"• {html.escape(s)}")

    patterns = snapshot.get("incident_patterns") or []
    if patterns:
        lines.extend(["", "<b>Incident patterns</b>"])
        for p in patterns[:4]:
            lines.append(
                f"• {html.escape(str(p.get('pattern', '?')))} "
                f"({p.get('occurrences', 0)}×)",
            )

    storylines = snapshot.get("top_storylines") or []
    if storylines:
        lines.extend(["", "<b>Top storylines</b>"])
        for s in storylines[:5]:
            lines.append(
                f"• <code>{html.escape(str(s.get('storyline_id', '?')))}</code> "
                f"({s.get('publish_count', 0)} posts)",
            )

    lines.extend(["", "<b>Operator workflow</b>"])
    lines.append(
        f"Overrides: {workflow.get('override_frequency', 0)} · "
        f"freeze/resume {workflow.get('freeze_events', 0)}/{workflow.get('resume_events', 0)} · "
        f"digest cmds {workflow.get('attention_commands', 0)}",
    )

    subs = trust.get("subsystems") or {}
    if subs:
        lines.extend(["", "<b>Subsystem bands</b>"])
        for name, m in list(subs.items())[:7]:
            lines.append(
                f"• {html.escape(name)}: <code>{html.escape(str(m.get('trust_band', '?')))}</code>",
            )

    return "\n".join(lines)
