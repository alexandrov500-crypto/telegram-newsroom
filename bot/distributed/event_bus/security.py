from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any


def cluster_signing_key() -> bytes | None:
    raw = os.getenv("CLUSTER_EVENT_SIGNING_KEY", "").strip()
    if not raw:
        return None
    return raw.encode("utf-8")


def sign_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    key = cluster_signing_key()
    if key is None:
        return payload
    stamped = dict(payload)
    stamped["_sig_ts"] = int(time.time())
    body = json.dumps(stamped, sort_keys=True, separators=(",", ":"))
    stamped["_sig"] = hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return stamped


def verify_event_payload(payload: dict[str, Any], *, max_skew_sec: int = 300) -> bool:
    key = cluster_signing_key()
    if key is None:
        return True
    signature = payload.pop("_sig", None)
    ts = payload.pop("_sig_ts", None)
    if not signature or ts is None:
        return False
    try:
        if abs(int(time.time()) - int(ts)) > max_skew_sec:
            return False
    except (TypeError, ValueError):
        return False
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    expected = hmac.new(key, body.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(str(signature), expected)
