from __future__ import annotations

import itertools
import json
import logging
import os
import threading
import time
from typing import Any

from ops.log_ring import append_log_line

_event_seq = itertools.count(1)
_event_lock = threading.Lock()

_TRUNC_KEYS = frozenset(
    {
        "sample",
        "detail",
        "error",
        "payload",
        "content",
        "sources",
        "text",
        "items_json",
        "user_prompt",
        "body_plain",
        "html_body",
        "full_plain",
        "choice",
        "unwrapped",
        "timings_json",
    }
)
_DEFAULT_MAX = 480


def reset_log_event_id_sequence_for_tests() -> None:
    """Reset monotonic event_id counter (pytest)."""
    global _event_seq
    with _event_lock:
        _event_seq = itertools.count(1)


def _next_event_id() -> str:
    with _event_lock:
        n = next(_event_seq)
    det = os.getenv("NEWSROOM_LOG_DETERMINISTIC_IDS", "").strip().lower() in {"1", "true", "yes"}
    if det:
        return f"evt-{n:06d}"
    return f"evt-{time.monotonic_ns()}-{n}"


def _truncate_str(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _subsystem_for_event(event: str) -> str:
    if not event:
        return "runtime"
    if "." in event:
        return event.split(".", 1)[0]
    return "runtime"


def _provenance_fields() -> dict[str, str]:
    try:
        from app.build_provenance import load_build_provenance
        from app.runtime_lifecycle import runtime_id, uptime_sec

        prov = load_build_provenance()
        return {
            "runtime_id": runtime_id(),
            "git_sha": prov.git_sha,
            "build_version": prov.build_version,
            "uptime_sec": str(round(uptime_sec(), 3)),
        }
    except Exception:
        return {}


def log_event(
    logger: logging.Logger,
    message: str,
    *,
    level: int = logging.INFO,
    subsystem: str | None = None,
    **fields: Any,
) -> None:
    """Emit normalized JSON log: timestamp, level, event, runtime_id, git_sha, uptime_sec, subsystem."""
    max_len = int(os.getenv("LOG_MAX_FIELD_LEN", str(_DEFAULT_MAX)))
    max_len = max(120, min(max_len, 4000))
    event = str(message)

    safe: dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": logging.getLevelName(level),
        "event": event,
        "subsystem": subsystem or _subsystem_for_event(event),
        **_provenance_fields(),
    }

    for k, v in fields.items():
        if k in safe:
            continue
        if isinstance(v, str):
            limit = max_len if k in _TRUNC_KEYS or len(v) > max_len * 2 else min(max_len * 2, 1200)
            safe[k] = _truncate_str(v, limit)
        elif isinstance(v, (bytes, bytearray)):
            safe[k] = f"<{type(v).__name__} len={len(v)}>"
        else:
            safe[k] = v

    try:
        from utils.operational_context import get_operational_log_fields

        for ok, ov in get_operational_log_fields().items():
            if ok not in safe:
                safe[ok] = ov
    except Exception:
        pass

    if "event_id" not in safe:
        safe["event_id"] = _next_event_id()

    try:
        from utils.security_redaction import redact_mapping, redaction_enabled

        if redaction_enabled():
            safe = redact_mapping(safe)
    except Exception:
        pass

    try:
        line = json.dumps(safe, ensure_ascii=False, default=str)
        if len(line) > max_len * 8:
            line = _truncate_str(line, max_len * 8)
    except TypeError:
        line = json.dumps({"event": event, "error": "json_encode_failed"}, default=str)

    append_log_line(line)
    logger.log(level, "%s", line)
