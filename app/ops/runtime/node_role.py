"""Mac control-plane vs VPS worker execution profile (zero-conflict polling)."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from enum import Enum
from typing import Any

from utils.structured_log import log_event

logger = __import__("logging").getLogger(__name__)


class RuntimeNodeRole(str, Enum):
    WORKER = "worker"
    CONTROL = "control"


@dataclass(frozen=True, slots=True)
class ExecutionProfile:
    """Effective runtime capabilities after node role resolution."""

    node_role: RuntimeNodeRole
    owner_id: str
    polling_enabled: bool
    scheduler_enabled: bool
    collector_enabled: bool
    publish_enabled: bool
    lane_workers_enabled: bool
    intent_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_role": self.node_role.value,
            "owner_id": self.owner_id,
            "polling_enabled": self.polling_enabled,
            "scheduler_enabled": self.scheduler_enabled,
            "collector_enabled": self.collector_enabled,
            "publish_enabled": self.publish_enabled,
            "lane_workers_enabled": self.lane_workers_enabled,
            "intent_path": self.intent_path,
        }


def _parse_role(raw: str) -> RuntimeNodeRole:
    v = (raw or "worker").strip().lower()
    if v in ("control", "control_plane", "mac", "management"):
        return RuntimeNodeRole.CONTROL
    return RuntimeNodeRole.WORKER


def _owner_id(settings: Any) -> str:
    explicit = os.getenv("RUNTIME_OWNER_ID", "").strip()
    if explicit:
        return explicit[:128]
    host = socket.gethostname()[:64]
    prof = str(getattr(settings, "deployment_profile", "") or "dev")[:32]
    return f"{host}:{prof}"


def _intent_override(runtime_state_dir: str) -> RuntimeNodeRole | None:
    from pathlib import Path

    p = Path(runtime_state_dir) / "execution_intent.json"
    if not p.is_file():
        return None
    try:
        import json

        data = json.loads(p.read_text(encoding="utf-8"))
        role = _parse_role(str(data.get("role") or ""))
        return role
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def resolve_execution_profile(settings: Any) -> ExecutionProfile:
    """Apply RUNTIME_NODE_ROLE and optional execution_intent.json override."""
    env_role = _parse_role(os.getenv("RUNTIME_NODE_ROLE", "worker"))
    intent = _intent_override(settings.runtime_state_dir)
    role = intent or env_role
    owner = _owner_id(settings)
    allow_pipeline = os.getenv("RUNTIME_CONTROL_ALLOW_PIPELINE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if role == RuntimeNodeRole.CONTROL:
        return ExecutionProfile(
            node_role=RuntimeNodeRole.CONTROL,
            owner_id=owner,
            polling_enabled=False,
            scheduler_enabled=allow_pipeline,
            collector_enabled=allow_pipeline,
            publish_enabled=False,
            lane_workers_enabled=allow_pipeline,
            intent_path=str(settings.runtime_state_dir) + "/execution_intent.json"
            if intent
            else None,
        )

    polling = bool(getattr(settings, "telegram_polling_enabled", True))
    return ExecutionProfile(
        node_role=RuntimeNodeRole.WORKER,
        owner_id=owner,
        polling_enabled=polling,
        scheduler_enabled=True,
        collector_enabled=True,
        publish_enabled=True,
        lane_workers_enabled=True,
        intent_path=str(settings.runtime_state_dir) + "/execution_intent.json"
        if intent
        else None,
    )


def apply_execution_profile_to_deps(profile: ExecutionProfile) -> None:
    from app.dependency_state import DependencyStatus, get_dependency_state

    deps = get_dependency_state()
    if profile.node_role == RuntimeNodeRole.CONTROL:
        deps.collector_enabled = profile.collector_enabled
        if not profile.collector_enabled:
            deps.set_dependency(
                "telethon",
                status=DependencyStatus.DEGRADED,
                detail="control_plane",
                recovery_hint="Set RUNTIME_NODE_ROLE=worker on execution host",
            )
        deps.telegram_mode = "control_plane"
        if not profile.polling_enabled:
            deps.polling_active = False


def log_execution_profile(profile: ExecutionProfile) -> None:
    log_event(logger, "execution.profile", **profile.to_dict())
    if profile.node_role == RuntimeNodeRole.CONTROL:
        logger.info(
            "Control plane mode: polling=OFF scheduler=%s (set RUNTIME_NODE_ROLE=worker for takeover)",
            profile.scheduler_enabled,
        )
