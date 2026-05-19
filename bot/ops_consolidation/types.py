from __future__ import annotations

from enum import Enum


class TelemetryTier(str, Enum):
    CRITICAL = "critical"
    OPERATIONAL = "operational"
    FORENSIC = "forensic"
    DEBUG = "debug"


class CommandTier(str, Enum):
    PRIMARY = "primary"
    REFERENCE = "reference"
    DIAGNOSTIC = "diagnostic"
    DEPRECATED_ALIAS = "deprecated_alias"
