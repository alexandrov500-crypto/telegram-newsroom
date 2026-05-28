"""Post-publish editorial feedback for ranking/source tuning."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = (runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime")).strip() or "var/runtime"
    p = Path(base).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p / "newsroom_feedback.jsonl"


def record_feedback_event(
    event: str,
    *,
    runtime_dir: str | None = None,
    draft_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    row = {
        "ts": time.time(),
        "event": event,
        "draft_id": draft_id,
        **(extra or {}),
    }
    try:
        with _path(runtime_dir).open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError:
        pass


def record_publish_success(
    *,
    draft_id: int,
    runtime_dir: str | None = None,
    signal_score: float | None = None,
    trust_score: float | None = None,
    manual_review: bool = False,
) -> None:
    record_feedback_event(
        "publish_success",
        runtime_dir=runtime_dir,
        draft_id=draft_id,
        extra={
            "signal_score": signal_score,
            "trust_score": trust_score,
            "manual_review": manual_review,
        },
    )


def record_manual_reject(draft_id: int, *, runtime_dir: str | None = None, reason: str = "") -> None:
    record_feedback_event(
        "manual_reject",
        runtime_dir=runtime_dir,
        draft_id=draft_id,
        extra={"reason": reason[:200]},
    )


def record_admin_override(draft_id: int, *, runtime_dir: str | None = None) -> None:
    record_feedback_event("admin_override", runtime_dir=runtime_dir, draft_id=draft_id)


def feedback_summary(*, runtime_dir: str | None = None, limit: int = 500) -> dict[str, Any]:
    path = _path(runtime_dir)
    if not path.is_file():
        return {"events": 0, "publish_success": 0, "manual_reject": 0, "admin_override": 0}
    counts: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()[-limit:]
        for ln in lines:
            row = json.loads(ln)
            ev = str(row.get("event") or "unknown")
            counts[ev] = counts.get(ev, 0) + 1
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "events": sum(counts.values()),
        "publish_success": counts.get("publish_success", 0),
        "manual_reject": counts.get("manual_reject", 0),
        "admin_override": counts.get("admin_override", 0),
        "emergency_deletion": counts.get("emergency_deletion", 0),
    }
