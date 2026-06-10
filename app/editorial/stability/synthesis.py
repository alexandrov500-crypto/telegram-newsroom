"""Editorial synthesis mode — digest blocks when no fresh events."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.editorial.stability.state import load_state, save_state


def _trend_topics(runtime_dir: str | None, limit: int = 5) -> list[str]:
    p = Path(runtime_dir or "var/runtime") / "editorial" / "trend_memory.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    clusters = data.get("clusters") or {}
    if not isinstance(clusters, dict):
        return []
    ranked = sorted(
        clusters.items(),
        key=lambda kv: float((kv[1] or {}).get("momentum_score") or 0),
        reverse=True,
    )
    out: list[str] = []
    for key, _row in ranked[:limit]:
        label = str(key).replace("_", " ").strip()
        if label:
            out.append(label[:80])
    return out


def _slot_label(now_local: datetime) -> tuple[str, str]:
    h = now_local.hour
    if h < 12:
        return "morning", "Утренняя сводка"
    if h < 18:
        return "midday", "Дневной снимок"
    return "evening", "Итоги дня"


def build_synthesis_post(
    runtime_dir: str | None,
    *,
    newsroom_tz: str = "Europe/Moscow",
    now: datetime | None = None,
) -> tuple[str, dict[str, Any]] | None:
    data = load_state(runtime_dir)
    now_ts = time.time()
    if now_ts - float(data.get("last_synthesis_ts") or 0) < 1800.0:
        return None

    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(newsroom_tz)
    except Exception:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Moscow")
    now_local = (now or datetime.now(UTC)).astimezone(tz)
    slot_key, slot_title = _slot_label(now_local)
    topics = _trend_topics(runtime_dir, limit=3)
    if not topics:
        topics = ["рынки", "экономика", "геополитика"]

    bullets = []
    for i, topic in enumerate(topics[:3], start=1):
        bullets.append(f"{i}. {topic.capitalize()} — ключевая тема для наблюдения.")

    body = (
        f"{slot_title}\n\n"
        f"3 вещи, которые стоит знать прямо сейчас:\n\n"
        + "\n".join(bullets)
        + "\n\n"
        "Что это значит: канал продолжает мониторинг — как только появится "
        "подтверждённое событие, вы получите полный разбор.\n\n"
        "#Контекст"
    )
    meta = {
        "synthesis_slot": slot_key,
        "synthesis_topics": topics,
        "post_type": "digest",
        "publishing_mode": "editorial_synthesis",
    }
    return body, meta


def mark_synthesis_emitted(runtime_dir: str | None) -> None:
    data = load_state(runtime_dir)
    data["last_synthesis_ts"] = time.time()
    save_state(runtime_dir, data)
