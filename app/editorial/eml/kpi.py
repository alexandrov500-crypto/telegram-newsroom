"""EML KPI snapshot."""

from __future__ import annotations

from app.editorial.eml.state import eml_snapshot


def eml_kpi_snapshot(runtime_dir: str | None = None) -> dict[str, object]:
    return {**eml_snapshot(runtime_dir), "core_kpis": {"cognitive_value": "attention_value_model", "revenue_index": "revenue_abstraction"}}
