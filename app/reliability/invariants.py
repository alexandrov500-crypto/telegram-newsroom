"""Operational invariants — explicit rules the runtime must uphold (Phase 3 freeze)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


class InvariantSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class InvariantCheck:
    invariant_id: str
    ok: bool
    detail: str = ""
    severity: InvariantSeverity = InvariantSeverity.WARNING


def _inv(
    invariant_id: str,
    ok: bool,
    *,
    detail: str = "",
    severity: InvariantSeverity = InvariantSeverity.WARNING,
) -> InvariantCheck:
    return InvariantCheck(invariant_id=invariant_id, ok=ok, detail=detail, severity=severity)


def check_runtime_config_invariants(settings: Any) -> list[InvariantCheck]:
    """Fail-fast config invariants (startup)."""
    from app.ops.runtime.node_role import RuntimeNodeRole, resolve_execution_profile

    profile = resolve_execution_profile(settings)
    checks: list[InvariantCheck] = []

    role = profile.node_role
    polling_env = bool(getattr(settings, "telegram_polling_enabled", True))

    checks.append(
        _inv(
            "INV-001-single-poller-config",
            not (role == RuntimeNodeRole.CONTROL and polling_env),
            detail="RUNTIME_NODE_ROLE=control must not enable Telegram polling",
            severity=InvariantSeverity.CRITICAL,
        )
    )
    checks.append(
        _inv(
            "INV-002-scheduler-control-plane",
            not (role == RuntimeNodeRole.CONTROL and profile.scheduler_enabled and not os.getenv("RUNTIME_CONTROL_ALLOW_PIPELINE")),
            detail="control plane must not run full scheduler unless RUNTIME_CONTROL_ALLOW_PIPELINE=true",
            severity=InvariantSeverity.CRITICAL,
        )
    )
    checks.append(
        _inv(
            "INV-003-publish-bounded-retries",
            int(os.getenv("FAILED_DRAFT_MAX_RETRIES", "5") or 5) <= 20,
            detail="FAILED_DRAFT_MAX_RETRIES must be <= 20",
        )
    )
    worker_url = (getattr(settings, "newsroom_worker_url", "") or os.getenv("NEWSROOM_WORKER_URL", "")).strip()
    if role == RuntimeNodeRole.WORKER and worker_url:
        checks.append(
            _inv(
                "INV-004-worker-url-on-worker",
                False,
                detail="NEWSROOM_WORKER_URL should be set on Mac control plane only, not worker",
                severity=InvariantSeverity.INFO,
            )
        )
    return checks


def check_runtime_state_invariants(settings: Any) -> list[InvariantCheck]:
    """Soft checks after boot (heartbeat / health)."""
    from app.dependency_state import get_dependency_state
    from app.reliability.auto_maintenance import publish_halted
    from app.ops.runtime.execution_lease import is_lease_stale, read_lease
    from db.reliability_repository import find_stuck_pipeline_ticks

    deps = get_dependency_state()
    checks: list[InvariantCheck] = [
        _inv(
            "INV-010-no-polling-conflict",
            not deps.conflict_detected,
            detail="telegram polling conflict detected",
            severity=InvariantSeverity.CRITICAL,
        ),
        _inv(
            "INV-011-maintenance-publish-halt",
            True,
            detail="auto_maintenance_active" if publish_halted(settings.runtime_state_dir) else "publish_allowed",
            severity=InvariantSeverity.INFO,
        ),
    ]
    lease = read_lease(settings.runtime_state_dir)
    if lease is not None:
        checks.append(
            _inv(
                "INV-012-execution-lease-fresh",
                not is_lease_stale(lease),
                detail=f"stale lease owner={lease.owner_id}",
                severity=InvariantSeverity.WARNING,
            )
        )
    return checks


async def check_async_state_invariants(settings: Any) -> list[InvariantCheck]:
    stuck = await find_stuck_pipeline_ticks(older_than_sec=float(os.getenv("PIPELINE_TICK_STUCK_SEC", "1200")))
    return [
        _inv(
            "INV-020-pipeline-tick-terminates",
            len(stuck) == 0,
            detail=f"stuck_ticks={len(stuck)}",
            severity=InvariantSeverity.CRITICAL,
        ),
    ]


def assert_startup_invariants(settings: Any) -> None:
    """Raise RuntimeError if any CRITICAL config invariant fails."""
    failed = [c for c in check_runtime_config_invariants(settings) if not c.ok]
    critical = [c for c in failed if c.severity == InvariantSeverity.CRITICAL]
    for c in failed:
        log_invariant_violation(c)
    if critical:
        msg = "Operational invariant violation:\n" + "\n".join(
            f"- {c.invariant_id}: {c.detail}" for c in critical
        )
        raise RuntimeError(msg)


def log_invariant_violation(check: InvariantCheck) -> None:
    log_event(
        logger,
        "invariant.violation",
        invariant_id=check.invariant_id,
        ok=check.ok,
        detail=check.detail[:300],
        severity=check.severity.value,
    )


async def run_heartbeat_invariant_checks(settings: Any) -> dict[str, Any]:
    """Non-fatal heartbeat checks; returns summary for ops panel."""
    checks = check_runtime_state_invariants(settings)
    checks.extend(await check_async_state_invariants(settings))
    violations = [c for c in checks if not c.ok]
    for c in violations:
        log_invariant_violation(c)
    return {
        "checked": len(checks),
        "violations": [{"id": c.invariant_id, "detail": c.detail, "severity": c.severity.value} for c in violations],
    }
