"""Weekly Growth Validation report for admin Telegram."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.growth_layer.prepublish.insights import build_prepublication_insights
from app.growth_layer.advisor_validation.reporting import build_advisor_effectiveness_snapshot
from app.growth_layer.policy.policy_reporting import recommendation_policy_section
from app.growth_layer.simulation.simulation_report import editorial_simulation_section
from app.growth_layer.strategy.strategy_reporting import editorial_strategy_section
from app.growth_layer.segments.segment_decision import evaluate_segment_strategy
from app.growth_layer.segments.segment_statistics import build_segment_performance
from app.growth_layer.editorial.api import get_segment_editorial_recommendations
from app.growth_layer.editorial.editorial_recommendations import generate_editorial_recommendations
from app.growth_layer.validation.calibration import ViralityCalibrationReport, build_virality_calibration
from app.growth_layer.validation.decision import FormatDecisionVerdict, evaluate_format_decision
from app.growth_layer.validation.rankings import build_growth_rankings
from app.growth_layer.validation.status import filter_final_rows
from db.growth_validation_repository import list_post_growth_validation


def _avg(rows: list[dict[str, Any]], key: str) -> float | None:
    vals = [float(r[key]) for r in rows if r.get(key) is not None]
    if not vals:
        return None
    return sum(vals) / len(vals)


def _fmt_pct(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:+.1f}%"


def _fmt_num(v: float | None, *, digits: int = 3) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}"


def _fmt_p(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:.3f}"


def _statistical_validation_section(decision: FormatDecisionVerdict) -> list[str]:
    lines = [
        "",
        "<b>STATISTICAL VALIDATION</b>",
        f"ERR Lift: {_fmt_pct(decision.err_lift_pct)} · p-value: {_fmt_p(decision.err_p_value)}",
        f"Forward Lift: {_fmt_pct(decision.forward_lift_pct)} · p-value: {_fmt_p(decision.forward_p_value)}",
        f"Effect Size: {escape(str(decision.effect_size))}",
        f"Statistically Significant: {'YES' if decision.statistically_significant else 'NO'}",
    ]
    if not decision.statistically_significant:
        lines.append("Recommendation blocked. Observed lift may be noise.")
    if decision.stability:
        lines.append("")
        lines.append("<b>Stability windows</b>")
        for window, data in decision.stability.items():
            if not isinstance(data, dict):
                continue
            sig = "YES" if data.get("statistically_significant") else "NO"
            lines.append(
                f"· {escape(window)}: ERR {_fmt_pct(data.get('err_lift_pct'))} "
                f"p={_fmt_p(data.get('err_p_value'))} · effect {escape(str(data.get('effect_size')))} · sig {sig}"
            )
    return lines


def _segment_line(verdict: dict[str, Any]) -> str:
    seg = escape(str(verdict.get("segment") or "?"))
    return (
        f"<b>{seg.title()}</b>\n"
        f"Growth ERR: {_fmt_num(verdict.get('growth_err'))} · CB ERR: {_fmt_num(verdict.get('cb_err'))}\n"
        f"Lift: {_fmt_pct(verdict.get('err_lift_pct'))} · P-value: {_fmt_p(verdict.get('p_value'))}\n"
        f"Recommendation: <code>{escape(str(verdict.get('recommended_mode')))}</code> "
        f"({escape(str(verdict.get('confidence')))} confidence, readiness {verdict.get('routing_readiness_score', 0)}/100)"
    )


def _segment_performance_section(all_rows: list[dict[str, Any]]) -> list[str]:
    perf = build_segment_performance(all_rows)
    if not perf:
        return ["", "<b>SEGMENT PERFORMANCE</b>", "Недостаточно данных по сегментам."]
    scored: list[tuple[float, dict[str, Any]]] = []
    for block in perf:
        verdict = evaluate_segment_strategy(str(block["segment"]), all_rows, final_only=False)
        lift = float(verdict.get("err_lift_pct") or 0.0)
        scored.append((lift, verdict))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [v for _, v in scored[:5]]
    worst = [v for _, v in sorted(scored, key=lambda x: x[0])[:5]]

    lines = ["", "<b>SEGMENT PERFORMANCE</b>", "<b>Top 5 segments by ERR lift</b>"]
    for verdict in top:
        lines.append(_segment_line(verdict))
    lines.extend(["", "<b>Worst 5 segments</b>"])
    for verdict in worst:
        lines.append(_segment_line(verdict))
    return lines


def _editorial_intelligence_section(all_rows: list[dict[str, Any]]) -> list[str]:
    if not all_rows:
        return ["", "<b>EDITORIAL INTELLIGENCE</b>", "Недостаточно данных."]
    recs = generate_editorial_recommendations(all_rows)
    segments = sorted(k for k in recs.keys() if k != "all")
    if not segments:
        segments = ["all"]
    lines = ["", "<b>EDITORIAL INTELLIGENCE</b>"]
    for segment in segments[:5]:
        data = recs.get(segment) or {}
        winning = data.get("winning_patterns") or []
        anti = data.get("anti_patterns") or []
        seg_title = escape(segment.replace("_", " ").title())
        lines.append(f"<b>{seg_title}</b>")
        lines.append("Winning patterns:")
        if winning:
            for w in winning[:4]:
                lines.append(f"+ {escape(w)}")
        else:
            lines.append("+ —")
        lines.append("Avoid:")
        if anti:
            for a in anti[:3]:
                lines.append(f"- {escape(a)}")
        else:
            lines.append("- —")
        api_recs = get_segment_editorial_recommendations(segment, rows=all_rows)
        if api_recs and api_recs[0] not in winning:
            lines.append(f"API: {escape(api_recs[0])}")
    return lines


def _prepublication_insights_section(insights: dict[str, Any]) -> list[str]:
    lines = ["", "<b>PRE-PUBLICATION INSIGHTS</b>"]
    if not insights or int(insights.get("sample_size") or 0) < 3:
        lines.append("Недостаточно данных (advice → validation join).")
        return lines
    avg = insights.get("average_alignment_score")
    lines.append(f"Average Alignment Score: <code>{avg}</code> (n={insights.get('sample_size')})")
    strong_lift = insights.get("strong_lift_pct")
    weak_lift = insights.get("weak_lift_pct")
    if strong_lift is not None:
        sign = "+" if strong_lift >= 0 else ""
        lines.append(f"Posts above 85: ERR {sign}{strong_lift}% vs cohort avg (n={insights.get('strong_count')})")
    if weak_lift is not None:
        sign = "+" if weak_lift >= 0 else ""
        lines.append(f"Posts below 60: ERR {sign}{weak_lift}% vs cohort avg (n={insights.get('weak_count')})")
    return lines


def _advisor_effectiveness_section(snapshot: dict[str, Any]) -> list[str]:
    lines = ["", "<b>ADVISOR EFFECTIVENESS</b>"]
    if not snapshot or int(snapshot.get("recommendations_shown") or 0) < 3:
        lines.append("Недостаточно данных по исходам рекомендаций.")
        return lines
    lines.append(f"Recommendations shown: <code>{snapshot.get('recommendations_shown')}</code>")
    lines.append(f"Adoption rate: <code>{snapshot.get('adoption_rate')}%</code>")
    lines.append(f"Advisor reliability: <code>{snapshot.get('advisor_reliability')}</code>")
    top = snapshot.get("top_recommendation")
    top_data = snapshot.get("top_recommendation_data") or {}
    if top:
        label = escape(str(top).replace("_", " "))
        lines.append(f"Top recommendation: {label}")
        if top_data.get("err_lift") is not None:
            sign = "+" if float(top_data["err_lift"]) >= 0 else ""
            lines.append(f"ERR lift: {sign}{top_data.get('err_lift')}%")
        if top_data.get("p_value") is not None:
            lines.append(f"P-value: <code>{top_data.get('p_value')}</code>")
    return lines


def _post_line(row: dict[str, Any], *, score_key: str) -> str:
    draft_id = int(row.get("draft_id") or 0)
    topic = escape(str(row.get("topic_bucket") or "general")[:24])
    src = escape(str(row.get("primary_source") or "—")[:20])
    score = row.get(score_key)
    fmt = escape(str(row.get("format_profile") or "?"))
    return f"#{draft_id} · {topic} · {src} · {fmt} · {score}"


def _aggregate_by_key(rows: list[dict[str, Any]], key: str, metric: str) -> list[tuple[str, float, int]]:
    buckets: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        k = str(r.get(key) or "unknown").strip() or "unknown"
        if r.get(metric) is not None:
            buckets[k].append(float(r[metric]))
    ranked = [(k, sum(v) / len(v), len(v)) for k, v in buckets.items() if v]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:5]


def _editorial_recommendations(
    *,
    week_rows: list[dict[str, Any]],
    decision: FormatDecisionVerdict,
    calibration: ViralityCalibrationReport,
) -> list[str]:
    tips: list[str] = []
    if decision.meets_threshold and decision.statistically_significant:
        tips.append("Growth Brief статистически опережает CB Brief — рассмотрите NEWSROOM_PUBLISH_FORMAT=growth_brief.")
    elif decision.err_lift_pct and decision.err_lift_pct >= 10.0:
        tips.append("Lift ERR наблюдается, но без статистической значимости — оставайтесь на hybrid.")
    else:
        tips.append("Оставайтесь на hybrid до статистически значимого подтверждения lift ERR/forwards.")

    if calibration.correlation is not None and calibration.correlation < 0.2:
        tips.append("Virality Engine слабо коррелирует с engagement — калибруйте веса signal ranking.")
    elif calibration.correlation is not None and calibration.correlation >= 0.35:
        tips.append("Virality Engine показывает полезную корреляцию с engagement — продолжайте hybrid routing.")

    top_topics = _aggregate_by_key(week_rows, "topic_bucket", "actual_engagement")
    if top_topics:
        tips.append(f"Усилить тему «{top_topics[0][0]}» — лучший avg engagement за неделю.")

    top_sources = _aggregate_by_key(week_rows, "primary_source", "actual_forward_rate")
    if top_sources and top_sources[0][0] not in {"", "unknown", "—"}:
        tips.append(f"Источник {top_sources[0][0]} даёт лучший forward rate — приоритизируйте в intake.")

    viral = [r for r in week_rows if str(r.get("format_profile")) == "growth_brief"]
    cb = [r for r in week_rows if str(r.get("format_profile")) == "cb_brief"]
    if viral and cb:
        v_eng = _avg(viral, "actual_engagement")
        c_eng = _avg(cb, "actual_engagement")
        if v_eng is not None and c_eng is not None and v_eng < c_eng * 0.9:
            tips.append("Growth Brief на этой неделе слабее по engagement — проверьте порог VIRALITY_VIRAL_MIN.")

    return tips[:5]


def build_weekly_growth_report(
    *,
    week_rows: list[dict[str, Any]],
    all_rows: list[dict[str, Any]],
    editorial_rows: list[dict[str, Any]] | None = None,
    advice_rows: list[dict[str, Any]] | None = None,
    advisor_snapshot: dict[str, Any] | None = None,
    policy_registry: dict[str, Any] | None = None,
    strategy_snapshot: dict[str, Any] | None = None,
    simulation_snapshot: dict[str, Any] | None = None,
    audience_delta_7d: int | None = None,
    now: datetime | None = None,
) -> str:
    """HTML report for admin bot."""
    now = now or datetime.now(timezone.utc)
    validated_week = filter_final_rows(week_rows)
    validated_all = filter_final_rows(all_rows)
    cal = build_virality_calibration(all_rows[:100])
    decision = evaluate_format_decision(all_rows[:100])
    rankings = build_growth_rankings(validated_week, limit=5)

    cb_rows = [r for r in validated_week if str(r.get("format_profile")) == "cb_brief"]
    growth_rows = [r for r in validated_week if str(r.get("format_profile")) == "growth_brief"]

    lines = [
        "<b>📊 Weekly Growth Report</b>",
        f"<i>{now.strftime('%Y-%m-%d %H:%M UTC')}</i>",
        "",
        "<b>1. Лучшие посты недели</b> (engagement)",
    ]
    for row in rankings.top_engagement[:5]:
        lines.append(_post_line(row, score_key="actual_engagement"))

    lines.extend(["", "<b>2. Лучшие темы недели</b>"])
    for topic, avg, n in _aggregate_by_key(validated_week, "topic_bucket", "actual_engagement"):
        lines.append(f"· {escape(topic)} — avg eng {avg:.3f} (n={n})")

    lines.extend(["", "<b>3. Лучшие источники недели</b>"])
    for src, avg, n in _aggregate_by_key(validated_week, "primary_source", "actual_forward_rate"):
        lines.append(f"· {escape(src)} — avg fwd rate {avg:.4f} (n={n})")

    lines.extend(
        [
            "",
            "<b>4. Growth Brief vs CB Brief</b>",
            f"CB: n={len(cb_rows)} ERR={_fmt_num(_avg(cb_rows, 'actual_err'))} fwd={_fmt_num(_avg(cb_rows, 'actual_forward_rate'), digits=4)}",
            f"Growth: n={len(growth_rows)} ERR={_fmt_num(_avg(growth_rows, 'actual_err'))} fwd={_fmt_num(_avg(growth_rows, 'actual_forward_rate'), digits=4)}",
            f"Lift ERR {_fmt_pct(decision.err_lift_pct)} · forwards {_fmt_pct(decision.forward_lift_pct)}",
            f"Рекомендация: <code>{escape(decision.recommended_mode)}</code> "
            f"(confidence {decision.confidence}, n={decision.sample_size}, {escape(decision.reason)})",
        ]
    )
    lines.extend(_statistical_validation_section(decision))
    lines.extend(
        [
            "",
            "<b>5. Топ по репостам</b>",
        ]
    )
    for row in rankings.top_forward_drivers[:5]:
        lines.append(_post_line(row, score_key="actual_forwards"))

    lines.extend(["", "<b>6. Топ по ERR</b>"])
    for row in rankings.top_err_drivers[:5]:
        lines.append(_post_line(row, score_key="actual_err"))

    lines.extend(_segment_performance_section(validated_all))
    editorial_source = filter_final_rows(editorial_rows) if editorial_rows is not None else validated_all
    lines.extend(_editorial_intelligence_section(editorial_source))
    prepub_insights = build_prepublication_insights(advice_rows or [], validated_all)
    lines.extend(_prepublication_insights_section(prepub_insights))
    if advisor_snapshot:
        lines.extend(_advisor_effectiveness_section(advisor_snapshot))
    if policy_registry:
        lines.extend(recommendation_policy_section(policy_registry))
    if strategy_snapshot:
        lines.extend(editorial_strategy_section(strategy_snapshot))
    if simulation_snapshot:
        lines.extend(editorial_simulation_section(simulation_snapshot))

    lines.extend(
        [
            "",
            "<b>Virality calibration (100 posts, FINAL only)</b>",
            f"n={cal.sample_size} · r={cal.correlation if cal.correlation is not None else '—'} · MAE={cal.mae if cal.mae is not None else '—'}",
            f"Tiers: {escape(str(cal.tier_distribution))}",
            f"Confusion: {escape(str(cal.tier_confusion_matrix))}",
        ]
    )
    if audience_delta_7d is not None:
        lines.extend(["", f"<b>Channel Δ7d:</b> {audience_delta_7d:+d} subscribers (proxy, channel-level)"])

    lines.extend(["", "<b>7. Рекомендации для редакции</b>"])
    for tip in _editorial_recommendations(week_rows=validated_week, decision=decision, calibration=cal):
        lines.append(f"· {escape(tip)}")

    return "\n".join(lines)


async def build_weekly_growth_report_from_db(
    session: AsyncSession,
    *,
    channel_id: int = 0,
) -> str:
    from sqlalchemy import select

    from app.growth_layer.editorial.enriched_rows import load_enriched_validation_rows
    from db.advisor_outcomes_repository import list_advisor_outcomes
    from db.growth_advice_repository import list_draft_growth_advice
    from db.models import ChannelAudienceSnapshot

    from app.growth_layer.policy.policy_registry import build_policy_registry
    from app.growth_layer.simulation.simulation_report import build_editorial_simulation_snapshot
    from app.growth_layer.strategy.strategy_reporting import build_editorial_strategy_snapshot

    all_rows = await list_post_growth_validation(session, limit=500, final_only=True)
    editorial_rows = await load_enriched_validation_rows(session, limit=500)
    advice_rows = await list_draft_growth_advice(session, limit=500)
    outcome_rows = await list_advisor_outcomes(session, limit=2000)
    advice_ids = {int(r["draft_id"]) for r in advice_rows if r.get("draft_id") is not None}
    advisor_snapshot = build_advisor_effectiveness_snapshot(
        outcome_rows,
        validation_rows=all_rows,
        advice_draft_ids=advice_ids,
    )
    policy_registry = build_policy_registry(outcome_rows, advice_rows=advice_rows, effectiveness_snapshot=advisor_snapshot)
    strategy_snapshot = build_editorial_strategy_snapshot(all_rows)
    simulation_snapshot = build_editorial_simulation_snapshot(strategy_snapshot)
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    week_rows = [
        r
        for r in all_rows
        if r.get("published_at") and datetime.fromisoformat(str(r["published_at"])) >= cutoff
    ]
    delta_7d: int | None = None
    if channel_id:
        snap = (
            await session.execute(
                select(ChannelAudienceSnapshot)
                .where(ChannelAudienceSnapshot.channel_id == int(channel_id))
                .order_by(ChannelAudienceSnapshot.captured_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snap is not None:
            delta_7d = int(snap.delta_7d)
    return build_weekly_growth_report(
        week_rows=week_rows,
        all_rows=all_rows,
        editorial_rows=editorial_rows,
        advice_rows=advice_rows,
        advisor_snapshot=advisor_snapshot,
        policy_registry=policy_registry,
        strategy_snapshot=strategy_snapshot,
        simulation_snapshot=simulation_snapshot,
        audience_delta_7d=delta_7d,
    )
