"""Read-only burn-in evaluation from pipeline_ticks + logs (no pipeline changes)."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FINISHED_STATUSES_OK = frozenset({"ok", "reject"})
TERMINAL_STATES = frozenset({"committed_draft", "committed_reject", "committed_idle"})


@dataclass(frozen=True)
class FinishedTickRow:
    id: int
    tick_id: str
    status: str
    terminal_state: str
    terminal_reason: str
    draft_id: int | None
    drafts_created: int
    failures: int
    duration_ms: int | None
    finished_at: str
    started_at: str


@dataclass(frozen=True)
class ActiveTickRow:
    id: int
    tick_id: str
    status: str
    started_at: str
    running_age_sec: float | None


def parse_tick_detail(detail_raw: str | None) -> dict[str, Any]:
    if not detail_raw:
        return {}
    try:
        data = json.loads(detail_raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def row_to_finished(row: tuple) -> FinishedTickRow:
    (
        rid,
        tick_id,
        status,
        drafts_created,
        failures,
        duration_ms,
        finished_at,
        started_at,
        detail_raw,
    ) = row
    detail = parse_tick_detail(detail_raw)
    draft_id = detail.get("draft_id")
    return FinishedTickRow(
        id=int(rid),
        tick_id=str(tick_id),
        status=str(status),
        terminal_state=str(detail.get("terminal_state") or ""),
        terminal_reason=str(detail.get("terminal_reason") or detail.get("summarize_idle") or "")[:240],
        draft_id=int(draft_id) if draft_id is not None else None,
        drafts_created=int(drafts_created or 0),
        failures=int(failures or 0),
        duration_ms=int(duration_ms) if duration_ms is not None else None,
        finished_at=str(finished_at or ""),
        started_at=str(started_at or ""),
    )


def _running_age_sec(started_at: str) -> float | None:
    if not started_at:
        return None
    try:
        started = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return round((datetime.now(timezone.utc) - started.astimezone(timezone.utc)).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


def fetch_finished_ticks(
    conn: sqlite3.Connection,
    *,
    limit: int = 20,
    since_id: int | None = None,
) -> list[FinishedTickRow]:
    if since_id is not None:
        rows = conn.execute(
            """
            SELECT id, tick_id, status, drafts_created, failures, duration_ms,
                   finished_at, started_at, detail_json
            FROM pipeline_ticks
            WHERE finished_at IS NOT NULL AND id >= ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(since_id), max(1, int(limit))),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, tick_id, status, drafts_created, failures, duration_ms,
                   finished_at, started_at, detail_json
            FROM pipeline_ticks
            WHERE finished_at IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
    return [row_to_finished(r) for r in rows]


def fetch_active_ticks(conn: sqlite3.Connection, *, limit: int = 20) -> list[ActiveTickRow]:
    rows = conn.execute(
        """
        SELECT id, tick_id, status, started_at
        FROM pipeline_ticks
        WHERE finished_at IS NULL
        ORDER BY id DESC
        LIMIT ?
        """,
        (max(1, int(limit)),),
    ).fetchall()
    out: list[ActiveTickRow] = []
    for rid, tick_id, status, started_at in rows:
        out.append(
            ActiveTickRow(
                id=int(rid),
                tick_id=str(tick_id),
                status=str(status),
                started_at=str(started_at or ""),
                running_age_sec=_running_age_sec(str(started_at or "")),
            )
        )
    return out


def tail_consecutive_finished_streak(all_ticks_newest_first: list[tuple[int, str | None]]) -> int:
    """Count finished ticks from highest id downward until first in-flight row."""
    n = 0
    for _id, finished_at in all_ticks_newest_first:
        if finished_at is None:
            break
        n += 1
    return n


def fetch_tail_streak_rows(
    conn: sqlite3.Connection,
    *,
    max_rows: int = 15,
    since_id: int | None = None,
) -> list[FinishedTickRow]:
    """Finished ticks forming the tail streak (newest ids, stop at first in-flight)."""
    if since_id is not None:
        rows = conn.execute(
            """
            SELECT id, tick_id, status, drafts_created, failures, duration_ms,
                   finished_at, started_at, detail_json
            FROM pipeline_ticks
            WHERE id >= ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(since_id), max(1, int(max_rows))),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, tick_id, status, drafts_created, failures, duration_ms,
                   finished_at, started_at, detail_json
            FROM pipeline_ticks
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, int(max_rows)),),
        ).fetchall()
    finished: list[FinishedTickRow] = []
    for row in rows:
        if row[6] is None:
            break
        finished.append(row_to_finished(row))
    return finished


def finished_metrics(finished: list[FinishedTickRow]) -> dict[str, Any]:
    if not finished:
        return {
            "count": 0,
            "ok": 0,
            "reject": 0,
            "other_status": 0,
            "with_terminal_state": 0,
            "committed_draft": 0,
            "committed_reject": 0,
            "committed_idle": 0,
            "missing_terminal_state": 0,
            "invalid_status": 0,
            "avg_duration_ms": None,
            "reject_rate": None,
        }
    ok = sum(1 for t in finished if t.status == "ok")
    reject = sum(1 for t in finished if t.status == "reject")
    other = len(finished) - ok - reject
    with_ts = sum(1 for t in finished if t.terminal_state)
    durations = [t.duration_ms for t in finished if t.duration_ms is not None]
    avg_d = round(sum(durations) / len(durations), 1) if durations else None
    reject_rate = round(reject / len(finished), 3) if finished else None
    return {
        "count": len(finished),
        "ok": ok,
        "reject": reject,
        "other_status": other,
        "with_terminal_state": with_ts,
        "committed_draft": sum(1 for t in finished if t.terminal_state == "committed_draft"),
        "committed_reject": sum(1 for t in finished if t.terminal_state == "committed_reject"),
        "committed_idle": sum(1 for t in finished if t.terminal_state == "committed_idle"),
        "missing_terminal_state": sum(1 for t in finished if not t.terminal_state),
        "invalid_status": other,
        "avg_duration_ms": avg_d,
        "reject_rate": reject_rate,
    }


def scan_log_contract(log_path: Path, *, tail_bytes: int = 8_000_000) -> dict[str, Any]:
    """Count contract violations and burn-in signals in log (reads tail of large files)."""
    base: dict[str, Any] = {
        "log_path": str(log_path),
        "available": False,
        "aborted_draft": 0,
        "pipeline_fatal_break": 0,
        "openai_summarize_failed": 0,
        "openai_429": 0,
        "rule_fallback": 0,
        "summarize_exit_reject": 0,
        "pipeline_terminal_state": 0,
        "collect_cycle_timeout": 0,
    }
    if not log_path.is_file():
        return base
    try:
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            if size > tail_bytes:
                fh.seek(size - tail_bytes)
                fh.readline()
            chunk = fh.read().decode("utf-8", errors="replace")
    except OSError as exc:
        base["error"] = str(exc)[:200]
        return base
    base.update(
        {
            "available": True,
            "tail_bytes_scanned": min(size, tail_bytes),
            "aborted_draft": len(re.findall(r"\baborted_draft\b", chunk)),
            "pipeline_fatal_break": len(re.findall(r"\bPIPELINE_FATAL_BREAK\b", chunk)),
            "openai_summarize_failed": len(re.findall(r"openai\.summarize_failed", chunk)),
            "openai_429": len(
                re.findall(r"429|RateLimit|rate_limit|insufficient_quota", chunk, re.I)
            ),
            "rule_fallback": len(
                re.findall(r"rule_fallback|failed_fallback_starvation|recovery=\"rule_fallback", chunk)
            ),
            "summarize_exit_reject": len(
                re.findall(r'"event":\s*"summarize_exit".*"outcome":\s*"reject"', chunk)
            ),
            "pipeline_terminal_state": len(re.findall(r"pipeline\.terminal_state", chunk)),
            "collect_cycle_timeout": len(re.findall(r"COLLECT_CYCLE_TIMEOUT", chunk)),
        }
    )
    return base


def fetch_head_in_flight_blocker(conn: sqlite3.Connection) -> ActiveTickRow | None:
    """Highest-id unfinished row below the newest finished tick (breaks tail streak)."""
    row = conn.execute(
        """
        SELECT id, tick_id, status, started_at
        FROM pipeline_ticks
        WHERE finished_at IS NULL
          AND id < COALESCE(
                (SELECT MAX(id) FROM pipeline_ticks WHERE finished_at IS NOT NULL),
                9223372036854775807
              )
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    rid, tick_id, status, started_at = row
    return ActiveTickRow(
        id=int(rid),
        tick_id=str(tick_id),
        status=str(status),
        started_at=str(started_at or ""),
        running_age_sec=_running_age_sec(str(started_at or "")),
    )


def active_stuck_warnings(
    active: list[ActiveTickRow],
    *,
    threshold_sec: float = 3600.0,
    head_blocker: ActiveTickRow | None = None,
) -> list[str]:
    """Warn only when the streak-blocking in-flight tick is stuck (not orphan rows)."""
    if head_blocker is None:
        return []
    age = head_blocker.running_age_sec
    if age is not None and age >= threshold_sec:
        return [
            f"head_in_flight_stuck:id={head_blocker.id} age_sec={age:.0f} "
            f"status={head_blocker.status} (blocks tail streak extension)"
        ]
    return []


def publishability_metrics(conn: sqlite3.Connection) -> dict[str, Any]:
    """Finished-tick and draft rates (read-only SQL)."""
    row = conn.execute(
        """
        SELECT
          SUM(CASE WHEN finished_at IS NOT NULL THEN 1 ELSE 0 END) AS finished_n,
          SUM(CASE WHEN finished_at IS NULL THEN 1 ELSE 0 END) AS running_n,
          SUM(CASE WHEN json_extract(detail_json,'$.terminal_state')='committed_draft'
              AND finished_at IS NOT NULL THEN 1 ELSE 0 END) AS draft_terminal_n,
          SUM(CASE WHEN json_extract(detail_json,'$.terminal_state')='committed_reject'
              AND finished_at IS NOT NULL THEN 1 ELSE 0 END) AS reject_terminal_n,
          SUM(CASE WHEN status='failed' AND finished_at IS NOT NULL THEN 1 ELSE 0 END) AS failed_n
        FROM pipeline_ticks
        """
    ).fetchone()
    finished_n, running_n, draft_t, reject_t, failed_n = (row or (0, 0, 0, 0, 0))
    reject_reasons: dict[str, int] = {}
    for (reason,) in conn.execute(
        """
        SELECT json_extract(detail_json,'$.terminal_reason')
        FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
          AND json_extract(detail_json,'$.terminal_state')='committed_reject'
        ORDER BY id DESC LIMIT 50
        """
    ).fetchall():
        key = str(reason or "unknown")[:48]
        reject_reasons[key] = reject_reasons.get(key, 0) + 1
    drafts_24h = conn.execute(
        """
        SELECT COUNT(*) FROM pipeline_ticks
        WHERE finished_at IS NOT NULL
          AND finished_at >= datetime('now', '-24 hours')
          AND json_extract(detail_json,'$.terminal_state')='committed_draft'
        """
    ).fetchone()[0]
    total_f = max(1, int(finished_n or 0))
    return {
        "finished_ticks": int(finished_n or 0),
        "running_ticks": int(running_n or 0),
        "committed_draft_terminal": int(draft_t or 0),
        "committed_reject_terminal": int(reject_t or 0),
        "failed_status_finished": int(failed_n or 0),
        "reject_rate": round(int(reject_t or 0) / total_f, 3),
        "draft_rate": round(int(draft_t or 0) / total_f, 3),
        "committed_draft_24h": int(drafts_24h or 0),
        "reject_reason_top": dict(sorted(reject_reasons.items(), key=lambda x: -x[1])[:8]),
    }


def evaluate_readiness(
    *,
    tail_streak: list[FinishedTickRow],
    streak_count: int,
    log_scan: dict[str, Any],
    min_ticks: int = 3,
    max_ticks: int = 7,
    require_golden: bool = False,
    require_drafts_24h: int = 0,
    publishability: dict[str, Any] | None = None,
    active_warnings: list[str] | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if active_warnings:
        reasons.extend(active_warnings)

    if streak_count < min_ticks:
        reasons.append(
            f"insufficient_consecutive_finished_ticks:{streak_count}<{min_ticks} "
            "(need finished tail from highest id without in-flight gap)"
        )

    for t in tail_streak[:max_ticks]:
        if t.status not in FINISHED_STATUSES_OK:
            reasons.append(f"tick_{t.id}_invalid_status:{t.status}")
        if not t.terminal_state:
            reasons.append(f"tick_{t.id}_missing_terminal_state")
        elif t.terminal_state not in TERMINAL_STATES:
            reasons.append(f"tick_{t.id}_unknown_terminal_state:{t.terminal_state}")

    if log_scan.get("available"):
        if int(log_scan.get("aborted_draft") or 0) > 0:
            reasons.append(f"log_aborted_draft_count:{log_scan['aborted_draft']}")
        if int(log_scan.get("pipeline_fatal_break") or 0) > 0:
            reasons.append(f"log_pipeline_fatal_break_count:{log_scan['pipeline_fatal_break']}")
    else:
        reasons.append("log_unavailable_for_contract_scan")

    if require_golden:
        golden = any(
            t.status == "ok" and t.terminal_state == "committed_draft" and t.draft_id is not None
            for t in tail_streak[:max_ticks]
        )
        if not golden:
            reasons.append("golden_tick_not_in_tail_streak")

    pub = publishability or {}
    drafts_24h = int(pub.get("committed_draft_24h") or 0)
    if require_drafts_24h > 0 and drafts_24h < require_drafts_24h:
        reasons.append(
            f"insufficient_committed_draft_24h:{drafts_24h}<{require_drafts_24h}"
        )

    fail_markers = (
        "log_aborted",
        "log_pipeline_fatal",
        "invalid_status",
        "missing_terminal_state",
        "unknown_terminal_state",
    )
    if any(any(m in r for m in fail_markers) for r in reasons):
        return "FAIL", reasons
    conditional_markers = (
        "insufficient_",
        "log_unavailable",
        "head_in_flight_stuck",
        "active_running_ticks",
        "insufficient_committed_draft",
        "golden_tick",
    )
    if any(any(r.startswith(m) for m in conditional_markers) for r in reasons):
        return "CONDITIONAL", reasons
    if reasons:
        return "CONDITIONAL", reasons
    return "PASS", []


def build_snapshot(
    conn: sqlite3.Connection,
    *,
    finished_limit: int = 15,
    log_path: Path | None = None,
    since_id: int | None = None,
    stuck_active_threshold_sec: float = 3600.0,
) -> dict[str, Any]:
    finished = fetch_finished_ticks(conn, limit=finished_limit, since_id=since_id)
    active = fetch_active_ticks(conn, limit=finished_limit)
    tail = fetch_tail_streak_rows(conn, max_rows=max(finished_limit, 15), since_id=since_id)
    if since_id is not None:
        tail_ids = conn.execute(
            """
            SELECT id, finished_at FROM pipeline_ticks
            WHERE id >= ?
            ORDER BY id DESC LIMIT ?
            """,
            (int(since_id), max(finished_limit, 15)),
        ).fetchall()
    else:
        tail_ids = conn.execute(
            "SELECT id, finished_at FROM pipeline_ticks ORDER BY id DESC LIMIT ?",
            (max(finished_limit, 15),),
        ).fetchall()
    streak_count = tail_consecutive_finished_streak(
        [(int(i), fin) for i, fin in tail_ids]
    )
    log_scan = scan_log_contract(log_path) if log_path else {"available": False}
    metrics = finished_metrics(finished)
    resolver_era = finished_metrics([t for t in finished if t.terminal_state])
    pub_metrics = publishability_metrics(conn)
    head_blocker = fetch_head_in_flight_blocker(conn)
    stuck = active_stuck_warnings(
        active,
        threshold_sec=stuck_active_threshold_sec,
        head_blocker=head_blocker,
    )
    orphan_active = [a.__dict__ for a in active if head_blocker is None or a.id != head_blocker.id]
    import os

    min_drafts = int(os.getenv("MIN_DRAFTS_PER_24H_TARGET", "0").strip() or "0")
    verdict, reasons = evaluate_readiness(
        tail_streak=tail,
        streak_count=streak_count,
        log_scan=log_scan,
        require_drafts_24h=min_drafts,
        publishability=pub_metrics,
        active_warnings=stuck,
    )
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "since_id": since_id,
        "verdict": verdict,
        "readiness_reasons": reasons,
        "tail_consecutive_finished_count": streak_count,
        "finished_metrics": metrics,
        "resolver_era_metrics": resolver_era,
        "publishability_metrics": pub_metrics,
        "log_contract": log_scan,
        "active_ticks": [a.__dict__ for a in active],
        "head_in_flight_blocker": head_blocker.__dict__ if head_blocker else None,
        "orphan_active_ticks": orphan_active,
        "finished_ticks": [f.__dict__ for f in finished],
        "tail_streak_finished": [f.__dict__ for f in tail],
    }
