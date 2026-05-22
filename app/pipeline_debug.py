"""Debug flags for end-to-end publication verification (production-safe, opt-in)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.dependency_state import get_dependency_state
from app.openai_circuit import get_openai_circuit
from app.operational_mode import OperationalMode, load_operational_mode


def _env_bool(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def is_first_post_debug_mode(settings: Any | None = None) -> bool:
    raw = os.getenv("RUNTIME_OPERATIONAL_MODE", "").strip().lower()
    if raw == OperationalMode.FIRST_POST_DEBUG.value:
        return True
    if settings is not None:
        rd = str(getattr(settings, "runtime_state_dir", "var/runtime"))
        try:
            return load_operational_mode(rd, settings) == OperationalMode.FIRST_POST_DEBUG
        except ValueError:
            pass
    return False


def is_force_single_publish_env() -> bool:
    return _env_bool("FORCE_SINGLE_PUBLISH")


def _force_done_marker(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "force_single_publish.done"


def force_single_publish_consumed(runtime_dir: str) -> bool:
    return _force_done_marker(runtime_dir).is_file()


def mark_force_single_publish_done(runtime_dir: str) -> None:
    p = _force_done_marker(runtime_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("ok\n", encoding="utf-8")


def pipeline_debug_active(settings: Any) -> bool:
    """True when debug publication guarantees are enabled for this tick."""
    if is_first_post_debug_mode(settings):
        return True
    if is_force_single_publish_env():
        rd = str(getattr(settings, "runtime_state_dir", "var/runtime"))
        return not force_single_publish_consumed(rd)
    return getattr(settings, "force_single_publish", False) and not force_single_publish_consumed(
        str(getattr(settings, "runtime_state_dir", "var/runtime"))
    )


def debug_bypass_suppressions(settings: Any) -> bool:
    return pipeline_debug_active(settings)


def debug_bypass_publish_gates(settings: Any) -> bool:
    return pipeline_debug_active(settings)


def ai_gating_snapshot(*, ctx: Any | None = None) -> dict[str, Any]:
    """Expose AI gate state for logs and /runtime/status."""
    deps = get_dependency_state()
    circuit = get_openai_circuit()
    circuit_open = not circuit.allow_request()
    ai_enabled = bool(deps.ai_pipeline_enabled) and not circuit_open
    block_reasons: list[str] = []
    if not deps.ai_pipeline_enabled:
        block_reasons.append("dependency_ai_pipeline_disabled")
    if circuit_open:
        block_reasons.append(f"openai_circuit_{circuit.state().value}")
    if deps.openai.status.value != "healthy":
        block_reasons.append(f"openai_dependency_{deps.openai.status.value}")
    ctx_ai = bool(getattr(ctx, "ai_pipeline_enabled", True)) if ctx is not None else True
    if not ctx_ai:
        block_reasons.append("pipeline_context_ai_disabled")
    settings = getattr(ctx, "settings", None) if ctx is not None else None
    fallback_active = bool(settings and pipeline_debug_active(settings))
    return {
        "ai_enabled": ai_enabled and ctx_ai,
        "ai_block_reason": ";".join(block_reasons) if block_reasons else None,
        "circuit_state": circuit.state().value,
        "circuit_open": circuit_open,
        "fallback_mode_active": fallback_active,
        "openai_dependency": deps.openai.status.value,
        "pipeline_debug_active": bool(settings and pipeline_debug_active(settings)),
        "force_single_publish": is_force_single_publish_env(),
        "first_post_debug_mode": is_first_post_debug_mode(settings),
    }
