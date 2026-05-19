from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def score_confidence_drift(db_path: Path, *, hours: int = 72) -> dict[str, Any]:
    """Detect oscillating editorial scores and priority ranks."""
    out: dict[str, Any] = {
        "editorial_quality_variance": 0.0,
        "priority_variance": 0.0,
        "unstable_classifications": 0,
        "drift_alert": "stable",
    }
    try:
        with sqlite3.connect(db_path, timeout=10) as conn:
            q_rows = conn.execute(
                """
                SELECT editorial_quality_score FROM editorial_quality_scores
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                ORDER BY created_at DESC LIMIT 40
                """,
                (hours,),
            ).fetchall()
            p_rows = conn.execute(
                """
                SELECT editorial_priority_score, urgency_class FROM editorial_priority_scores
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                ORDER BY created_at DESC LIMIT 40
                """,
                (hours,),
            ).fetchall()
            m_rows = conn.execute(
                """
                SELECT follow_up_kind FROM editorial_story_events
                WHERE created_at >= datetime('now', printf('-%d hours', ?))
                ORDER BY created_at DESC LIMIT 40
                """,
                (hours,),
            ).fetchall()
    except sqlite3.OperationalError:
        return out

    def _variance(vals: list[float]) -> float:
        if len(vals) < 2:
            return 0.0
        mean = sum(vals) / len(vals)
        return sum((v - mean) ** 2 for v in vals) / len(vals)

    q_scores = [float(r[0]) for r in q_rows]
    p_scores = [float(r[0]) for r in p_rows]
    out["editorial_quality_variance"] = round(_variance(q_scores), 4)
    out["priority_variance"] = round(_variance(p_scores), 4)

    kinds = [str(r[0]) for r in m_rows]
    if len(kinds) >= 6:
        switches = sum(1 for i in range(1, len(kinds)) if kinds[i] != kinds[i - 1])
        out["unstable_classifications"] = switches
        if switches >= len(kinds) * 0.6:
            out["drift_alert"] = "classification_unstable"

    if out["priority_variance"] > 0.04 or out["editorial_quality_variance"] > 0.03:
        out["drift_alert"] = "scoring_oscillation"
    return out
