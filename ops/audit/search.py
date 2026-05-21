"""Unified audit search across ledgers, journals, and timelines."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Literal

AuditEntity = Literal[
    "publish",
    "suppression",
    "operator_action",
    "policy_match",
    "drift_warning",
    "anomaly",
    "calibration",
    "runtime_recovery",
    "control_action",
    "timeline",
]


def _in_range(ts_unix: float, since: float | None, until: float | None) -> bool:
    if since is not None and ts_unix < since:
        return False
    if until is not None and ts_unix > until:
        return False
    return True


def _read_jsonl(path: Path, limit: int = 2000) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows[-limit:]


def _normalize_row(
    *,
    entity: str,
    ts_unix: float,
    runtime_id: str,
    summary: str,
    source: str = "",
    topic: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "entity": entity,
        "ts_unix": ts_unix,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts_unix)),
        "runtime_id": runtime_id,
        "summary": summary[:240],
        "source": source[:80],
        "topic": topic[:80],
        "payload": payload or {},
    }


def collect_audit_records(runtime_dir: str) -> list[dict[str, Any]]:
    rd = Path(runtime_dir).expanduser().resolve()
    out: list[dict[str, Any]] = []

    from editorial.governance.ledger import query_decisions

    for row in query_decisions(str(rd), limit=500):
        ts = float(row.get("ts_unix") or 0)
        dt = str(row.get("decision_type") or "")
        entity: str = "suppression"
        if "publish" in dt or "reject" in dt:
            entity = "publish"
        elif dt.startswith("operator"):
            entity = "operator_action"
        elif "policy" in dt or row.get("policy_matches"):
            entity = "policy_match"
        out.append(
            _normalize_row(
                entity=entity,
                ts_unix=ts,
                runtime_id=str(row.get("runtime_id") or ""),
                summary=f"{dt}:{row.get('outcome')}",
                topic=str(row.get("subject_id") or "")[:80],
                payload=row,
            )
        )

    from ops.resilience.publish_journal import journal_tail

    for row in journal_tail(str(rd), limit=300):
        ts = float(row.get("ts_unix") or 0)
        out.append(
            _normalize_row(
                entity="publish",
                ts_unix=ts,
                runtime_id="",
                summary=f"publish:{row.get('state')}",
                payload=row,
            )
        )

    for row in _read_jsonl(rd / "ops" / "action_journal.jsonl"):
        ts = float(row.get("ts_unix") or 0)
        out.append(
            _normalize_row(
                entity="control_action",
                ts_unix=ts,
                runtime_id=str(row.get("runtime_id") or ""),
                summary=str(row.get("action") or ""),
                payload=row,
            )
        )

    from dashboard.timeline import load_timeline_tail

    for ev in load_timeline_tail(str(rd), limit=200):
        ts = float(ev.get("ts") or 0)
        kind = str(ev.get("kind") or "")
        entity = "timeline"
        if "drift" in kind:
            entity = "drift_warning"
        elif "recover" in kind or "snapshot" in kind:
            entity = "runtime_recovery"
        elif "suppress" in kind:
            entity = "suppression"
        pl = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        out.append(
            _normalize_row(
                entity=entity,
                ts_unix=ts,
                runtime_id="",
                summary=kind,
                topic=str(pl.get("topic_hint") or pl.get("topic") or "")[:80],
                payload=ev,
            )
        )

    from ops.runtime_timeline import timeline_snapshot

    for row in timeline_snapshot(limit=150):
        d = row.to_dict() if hasattr(row, "to_dict") else dict(row)
        ts = float(d.get("ts_unix") or 0)
        kind = str(d.get("kind") or "")
        ent = "anomaly" if "watchdog" in kind or "alert" in kind else "timeline"
        out.append(
            _normalize_row(
                entity=ent,
                ts_unix=ts,
                runtime_id="",
                summary=kind,
                payload=d,
            )
        )

    drift_path = rd / "editorial_drift_snapshots.json"
    if drift_path.is_file():
        try:
            data = json.loads(drift_path.read_text(encoding="utf-8"))
            for snap in (data.get("history") or [])[-20:]:
                if not isinstance(snap, dict):
                    continue
                ts = time.mktime(time.strptime(str(snap.get("ts")), "%Y-%m-%dT%H:%M:%SZ")) if snap.get("ts") else 0
                if snap.get("alert"):
                    out.append(
                        _normalize_row(
                            entity="drift_warning",
                            ts_unix=ts or time.time(),
                            runtime_id="",
                            summary="editorial_drift:" + ",".join(snap.get("warnings") or []),
                            payload=snap,
                        )
                    )
        except (OSError, json.JSONDecodeError, ValueError):
            pass

    return out


def search_audit(
    runtime_dir: str,
    *,
    entity: str | None = None,
    runtime_id: str | None = None,
    source: str | None = None,
    topic: str | None = None,
    since_unix: float | None = None,
    until_unix: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    rows = collect_audit_records(runtime_dir)
    filtered: list[dict[str, Any]] = []
    for r in rows:
        ts = float(r.get("ts_unix") or 0)
        if not _in_range(ts, since_unix, until_unix):
            continue
        if entity and r.get("entity") != entity:
            continue
        if runtime_id and r.get("runtime_id") and r.get("runtime_id") != runtime_id:
            continue
        if source and source.lower() not in json.dumps(r, default=str).lower():
            continue
        if topic and topic.lower() not in (str(r.get("topic") or "") + json.dumps(r.get("payload") or {}, default=str)).lower():
            continue
        filtered.append(r)
    filtered.sort(key=lambda x: (-float(x.get("ts_unix") or 0), str(x.get("entity")), str(x.get("summary"))))
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "limit": limit,
        "offset": offset,
        "results": page,
    }
