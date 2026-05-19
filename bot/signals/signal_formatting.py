from __future__ import annotations

import html

from bot.storage.signal_repository import AnomalyRecord, SignalRecord


def _esc(text: str) -> str:
    return html.escape(text.strip())


def format_signal_list(signals: list[SignalRecord], *, title: str) -> str:
    if not signals:
        return f"{title}\n\nNo active signals."
    lines = [title, ""]
    for idx, sig in enumerate(signals, start=1):
        ents = ", ".join(_esc(e) for e in sig.entities[:4])
        ent_part = f" [{ents}]" if ents else ""
        lines.append(
            f"{idx}. #{sig.id} {_esc(sig.signal_type)} "
            f"conf={sig.confidence:.2f} vel={sig.velocity_score:.2f}{ent_part}"
        )
        if sig.title:
            lines.append(f"   {_esc(sig.title[:100])}")
        if sig.editorial_action:
            lines.append(f"   action={sig.editorial_action}")
    return "\n".join(lines)


def format_anomaly_list(anomalies: list[AnomalyRecord]) -> str:
    if not anomalies:
        return "No anomalies detected recently."
    lines = ["Recent anomalies:", ""]
    for row in anomalies:
        lines.append(
            f"- {_esc(row.anomaly_type)} [{_esc(row.scope)}:{_esc(row.scope_key)}] "
            f"sev={row.severity:.2f} obs={row.observed_value} base={row.baseline_value}"
        )
    return "\n".join(lines)


def format_forecast_list(forecasts: list[dict]) -> str:
    if not forecasts:
        return "No forecasts available."
    lines = ["Escalation forecasts:", ""]
    for row in forecasts:
        lines.append(
            f"- story={row.get('story_id')} "
            f"p={float(row['forecast_probability']):.2f} "
            f"impact={float(row['expected_impact']):.2f} "
            f"reach={float(row['expected_reach']):.2f}"
        )
    return "\n".join(lines)


def format_credibility_list(rows: list[dict]) -> str:
    if not rows:
        return "No credibility snapshots yet."
    lines = ["Source credibility (highest risk first):", ""]
    for row in rows:
        lines.append(
            f"- {_esc(str(row['source_name']))} "
            f"cred={float(row['credibility_score']):.2f} "
            f"risk={float(row['risk_score']):.2f} "
            f"sens={float(row['sensationalism']):.2f}"
        )
    return "\n".join(lines)
