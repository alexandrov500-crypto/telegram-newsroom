from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from bot.ops_evidence.report import build_weekly_operational_review, build_weekly_review_html
from bot.ops_evidence.repository import EvidenceReviewRepository
from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)


def _enabled() -> bool:
    raw = os.getenv("OPS_EVIDENCE_REVIEW_ENABLED", "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


def weekly_review_payload(
    *,
    db_path: Path | None = None,
    hours: int = 168,
    base_url: str = "http://127.0.0.1:8080",
    persist: bool = True,
) -> dict[str, Any]:
    if not _enabled():
        return {"status": "disabled", "message": "OPS_EVIDENCE_REVIEW_ENABLED is off"}
    path = init_database(db_path or default_db_path())
    return build_weekly_operational_review(
        path,
        hours=hours,
        base_url=base_url,
        persist=persist,
    )


def weekly_review_html(
    *,
    db_path: Path | None = None,
    hours: int = 168,
    base_url: str = "http://127.0.0.1:8080",
) -> str:
    snap = weekly_review_payload(db_path=db_path, hours=hours, base_url=base_url)
    if snap.get("status") == "disabled":
        return "<b>Weekly review</b>\n\nEvidence review layer is disabled."
    return build_weekly_review_html(snap)


def archive_weekly_review(
    *,
    db_path: Path | None = None,
    root: Path | None = None,
) -> Path | None:
    """Persist JSON artifact under var/ops/weekly/ in addition to DB."""
    try:
        from bot.config import project_root

        snap = weekly_review_payload(db_path=db_path, persist=True)
        out_dir = (root or project_root() / "var" / "ops" / "weekly")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{snap.get('week_id', 'unknown')}.json"
        path.write_text(json.dumps(snap, indent=2, default=str) + "\n", encoding="utf-8")
        return path
    except Exception:
        logger.debug("event=weekly_review_archive_failed")
        return None


def load_archived_review(week_id: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    path = init_database(db_path or default_db_path())
    return EvidenceReviewRepository(path).load_review(week_id)
