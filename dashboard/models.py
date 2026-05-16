"""Typed-ish payloads for read-only operational dashboards (plain dicts in practice)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DashboardSection:
    """Named block inside a dashboard bundle."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "data": dict(self.data)}


@dataclass(slots=True)
class OperationalDashboardBundle:
    """Aggregate returned by ``build_operational_dashboard_bundle``."""

    schema_version: int = 1
    generated_at_unix: float = 0.0
    runtime: dict[str, Any] = field(default_factory=dict)
    editorial: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    timeline_tail: list[dict[str, Any]] = field(default_factory=list)
    editorial_operational: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at_unix": self.generated_at_unix,
            "runtime": dict(self.runtime),
            "editorial": dict(self.editorial),
            "warnings": list(self.warnings),
            "timeline_tail": list(self.timeline_tail),
            "editorial_operational": dict(self.editorial_operational),
        }
