"""Single source of truth for release / compatibility metadata (no secrets)."""

from __future__ import annotations

from typing import Any

# Re-export package version (SSOT: newsroom._version.VERSION).
from newsroom._version import VERSION as APP_VERSION

# JSON files under RUNTIME_STATE_DIR: bump when breaking on-disk shape.
RUNTIME_STATE_SCHEMA_VERSION = 1

# operational_timeline.json schema
OPERATIONAL_TIMELINE_SCHEMA_VERSION = 1

# Reserved for future prompt bundle compatibility (editorial / AI layer).
PROMPT_SCHEMA_VERSION = 1


def public_metadata() -> dict[str, Any]:
    """Fields safe for logs, /ready, and ops JSON."""
    return {
        "app_version": APP_VERSION,
        "runtime_state_schema_version": RUNTIME_STATE_SCHEMA_VERSION,
        "operational_timeline_schema_version": OPERATIONAL_TIMELINE_SCHEMA_VERSION,
        "prompt_schema_version": PROMPT_SCHEMA_VERSION,
    }
