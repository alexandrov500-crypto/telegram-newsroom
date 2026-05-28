"""Release metadata persistence for launch evidence."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "release_metadata.json"


def update_release_metadata(runtime_dir: str, payload: dict[str, Any]) -> Path:
    p = _path(runtime_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    prev: dict[str, Any] = {}
    if p.is_file():
        try:
            prev = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(prev, dict):
                prev = {}
        except (OSError, json.JSONDecodeError):
            prev = {}
    hist_stage = list(prev.get("rollout_stage_history") or [])
    hist_burn = list(prev.get("burnin_verdict_history") or [])
    stage = str(payload.get("rollout_stage") or "")
    burn = str(payload.get("burnin_verdict") or "")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if stage:
        hist_stage.append({"at": now, "value": stage})
    if burn:
        hist_burn.append({"at": now, "value": burn})
    out = {
        "RELEASE_READY": True,
        "release_timestamp": now,
        "rollout_stage_history": hist_stage[-40:],
        "burnin_verdict_history": hist_burn[-40:],
        "final_readiness_snapshot": payload,
    }
    p.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def release_metadata_payload(runtime_dir: str) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


async def run_release_metadata_heartbeat(settings: Any) -> dict[str, Any]:
    from app.observability.burnin_validation import load_burnin_validation
    from app.observability.public_readiness import evaluate_final_public_readiness
    from app.ops.controlled_rollout import current_rollout_stage
    from utils.database_url import sqlite_path_from_url

    dbp = sqlite_path_from_url(os.getenv("DATABASE_URL", settings.database_url))
    readiness = evaluate_final_public_readiness(
        db_path=Path(dbp) if dbp else None,
        runtime_dir=Path(settings.runtime_state_dir),
        log_path=Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log")),
    )
    burn = load_burnin_validation(settings.runtime_state_dir)
    p = update_release_metadata(
        settings.runtime_state_dir,
        {
            "rollout_stage": current_rollout_stage().value,
            "burnin_verdict": burn.get("burnin_verdict") or burn.get("BURNIN_VERDICT"),
            "final_public_readiness": readiness.get("FINAL_PUBLIC_READINESS"),
            "blockers": readiness.get("blockers"),
        },
    )
    return {"path": str(p), "final_public_readiness": readiness.get("FINAL_PUBLIC_READINESS")}
