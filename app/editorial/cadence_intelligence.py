"""Publish cadence intelligence — bursts, spam clusters, duplicate themes."""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path
from typing import Any

from editorial.intelligence_store import cadence_state_path, load_json, save_json

_THEME_STOP = frozenset(
    "и в на по что это как для из при без не да нет the a an of to in on".split()
)


def _theme_key(text: str) -> str:
    words = re.findall(r"[a-zа-яё0-9]{4,}", (text or "").lower())
    kept = [w for w in words if w not in _THEME_STOP][:12]
    blob = " ".join(kept) or (text or "")[:80]
    return hashlib.sha256(blob.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _token_set(text: str) -> set[str]:
    return set(re.findall(r"[a-zа-яё0-9]{4,}", (text or "").lower()))


def _intel_path(runtime_dir: str | None) -> Path | None:
    if not runtime_dir:
        return None
    return cadence_state_path(runtime_dir).with_name("cadence_intel.json")


def _load_intel(runtime_dir: str | None) -> dict[str, Any]:
    path = _intel_path(runtime_dir)
    if not path:
        return {"version": 1, "themes": [], "titles": []}
    return load_json(path, {"version": 1, "themes": [], "titles": []})


def _save_intel(runtime_dir: str | None, data: dict[str, Any]) -> None:
    path = _intel_path(runtime_dir)
    if not path:
        return
    save_json(path, data)


def evaluate_cadence_intelligence(
    settings: Any,
    runtime_dir: str | None,
    *,
    content: str,
    topic_key: str = "",
    is_breaking: bool = False,
    now_unix: float | None = None,
) -> tuple[bool, list[str]]:
    """
    Returns (block_publish, reasons). Complements editorial.cadence burst rules.
    """
    if is_breaking:
        return False, []

    reasons: list[str] = []
    now = float(now_unix or time.time())
    data = _load_intel(runtime_dir)
    themes: list[dict[str, Any]] = list(data.get("themes") or [])
    titles: list[dict[str, Any]] = list(data.get("titles") or [])

    theme = topic_key[:20] or _theme_key(content)
    tokens = _token_set(content)

    recent_themes = [t for t in themes if now - float(t.get("ts") or 0) <= 7200]
    same_theme = sum(1 for t in recent_themes if str(t.get("key") or "") == theme)
    if same_theme >= 3:
        reasons.append("cadence_intel_repeated_theme")

    for t in recent_themes[-12:]:
        prev = _token_set(str(t.get("snippet") or ""))
        if _jaccard(tokens, prev) >= 0.72:
            reasons.append("cadence_intel_near_identical_story")
            break

    burst_win = float(getattr(settings, "publish_burst_window_sec", 120.0) or 120.0)
    burst_max = int(getattr(settings, "publish_burst_max_messages", 4) or 4)
    recent_pub = [float(t.get("ts") or 0) for t in titles if now - float(t.get("ts") or 0) <= burst_win]
    if len(recent_pub) >= burst_max:
        reasons.append("cadence_intel_burst_cap")

    if len(recent_pub) >= max(2, burst_max - 1) and same_theme >= 1:
        reasons.append("cadence_intel_spam_cluster")

    return bool(reasons), reasons


def record_cadence_intelligence(
    runtime_dir: str | None,
    *,
    content: str,
    topic_key: str = "",
) -> None:
    if not runtime_dir:
        return
    now = time.time()
    data = _load_intel(runtime_dir)
    themes = list(data.get("themes") or [])
    themes.insert(
        0,
        {
            "ts": now,
            "key": topic_key[:20] or _theme_key(content),
            "snippet": (content or "")[:240],
        },
    )
    data["themes"] = themes[:40]
    titles = list(data.get("titles") or [])
    titles.insert(0, {"ts": now, "snippet": (content or "")[:120]})
    data["titles"] = titles[:40]
    _save_intel(runtime_dir, data)
