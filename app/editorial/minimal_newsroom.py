"""Emergency minimal pipeline mode — prove physical publish path works."""

from __future__ import annotations

import os

from app.recovery.pipeline_overrides import is_force_publish_bypass, is_minimal_pipeline_mode


def is_minimal_newsroom_mode() -> bool:
    return is_minimal_pipeline_mode()


def bypass_final_publish_gate() -> bool:
    return is_minimal_newsroom_mode() or is_force_publish_bypass()


def public_output_lock_enforce() -> bool:
    """When minimal mode: log lock violations only, do not block."""
    if is_minimal_newsroom_mode():
        return os.getenv("MINIMAL_LOCK_ENFORCE", "false").strip().lower() in {"1", "true", "yes", "on"}
    return True


def bypass_signal_and_governance() -> bool:
    return is_minimal_newsroom_mode()
