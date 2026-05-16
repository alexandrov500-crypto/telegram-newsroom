from __future__ import annotations

import itertools
import json
import logging
import os
import threading
import time
from typing import Any

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


def log_event(logger: logging.Logger, message: str, **fields: Any) -> None:
    """Structured log line; long strings truncated to limit log volume."""
    max_len = int(os.getenv("LOG_MAX_FIELD_LEN", str(_DEFAULT_MAX)))
    max_len = max(120, min(max_len, 4000))

    if not fields:
        logger.info(message)
        return

    safe: dict[str, Any] = {}
    for k, v in fields.items():
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

    if "event_id" not in fields:
        safe["event_id"] = _next_event_id()

    try:
        from utils.security_redaction import redact_mapping, redaction_enabled

        if redaction_enabled():
            safe = redact_mapping(safe)
    except Exception:
        pass

    try:
        payload = json.dumps(safe, ensure_ascii=False, default=str)
        if len(payload) > max_len * 6:
            payload = _truncate_str(payload, max_len * 6)
    except TypeError:
        payload = str(safe)
    logger.info("%s | %s", message, payload)
