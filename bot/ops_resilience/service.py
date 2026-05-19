from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from bot.ops_resilience.coordinator import evaluate_resilience_tick
from bot.ops_resilience.report import build_resilience_status_html
from bot.ops_resilience.repository import ResilienceRepository
from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    raw = os.getenv("OPS_RESILIENCE_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _interval_sec() -> int:
    try:
        return int(os.getenv("OPS_RESILIENCE_INTERVAL_SEC", "120"))
    except ValueError:
        return 120


def resilience_status_payload(
    *,
    db_path: Path | None = None,
    base_url: str = "http://127.0.0.1:8080",
) -> dict[str, Any]:
    if not _enabled():
        return {"status": "disabled"}
    path = init_database(db_path or default_db_path())
    snap = evaluate_resilience_tick(db_path=path, base_url=base_url, persist=True)
    return {"status": "ok", **snap}


def resilience_status_html(
    *,
    db_path: Path | None = None,
    base_url: str = "http://127.0.0.1:8080",
) -> str:
    payload = resilience_status_payload(db_path=db_path, base_url=base_url)
    if payload.get("status") == "disabled":
        return "<b>Resilience layer</b>\n\nDisabled (OPS_RESILIENCE_ENABLED=false)."
    return build_resilience_status_html(payload)


def load_persisted_state(db_path: Path | None = None) -> dict[str, Any] | None:
    path = init_database(db_path or default_db_path())
    return ResilienceRepository(path).load_state()


async def resilience_evaluation_loop(db_path: Path | None = None) -> None:
    """Background resilience tick — lightweight, fail-open."""
    if not _enabled():
        return
    path = init_database(db_path or default_db_path())
    base = os.getenv("HEALTH_HTTP_BASE", "http://127.0.0.1:8080")
    interval = _interval_sec()
    while True:
        try:
            await asyncio.to_thread(
                evaluate_resilience_tick,
                db_path=path,
                base_url=base,
                persist=True,
            )
        except Exception:
            logger.debug("event=resilience_tick_failed")
        await asyncio.sleep(interval)
