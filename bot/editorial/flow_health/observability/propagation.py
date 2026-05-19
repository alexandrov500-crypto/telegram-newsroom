from __future__ import annotations

from typing import Any

_CANONICAL_LAYERS = (
    "certification",
    "freeze_registry",
    "operational_memory",
    "doctrine",
    "strategic_resilience",
    "minimalism",
    "closure",
    "legacy",
)

_TOP_LEVEL_EXPORTS: tuple[tuple[str, str, str | tuple[str, ...]], ...] = (
    ("operational_confidence_index", "certification", ("operational_confidence", "operational_confidence_index")),
    ("ultra_quiet_digest", "freeze_registry", "ultra_quiet_digest"),
    ("operational_closure_candidate", "closure", "operational_closure_candidate"),
    ("succession_readiness", "legacy", "succession_readiness"),
    ("architectural_compression_score", "minimalism", "architectural_compression_score"),
    ("strategic_resilience_index", "strategic_resilience", "strategic_resilience_index"),
)


def _nested_field(layer: dict[str, Any], path: str | tuple[str, ...]) -> Any:
    cur: Any = layer
    if isinstance(path, tuple):
        for key in path:
            cur = (cur or {}).get(key) if isinstance(cur, dict) else None
        return cur
    return layer.get(path)


def verify_canonical_propagation(
    *,
    enriched_governance: dict[str, Any] | None = None,
    collector_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Snapshot-time check: downstream reads match enriched governance."""
    gov = enriched_governance or {}
    ctx = collector_ctx or {}
    signals: list[str] = []

    for ctx_key, layer_key, field_path in _TOP_LEVEL_EXPORTS:
        nested_val = _nested_field(gov.get(layer_key) or {}, field_path)
        top_val = ctx.get(ctx_key)
        if nested_val is not None and top_val is None and layer_key in gov:
            signals.append(f"stale_read_{ctx_key}")
        if top_val is not None and nested_val is not None and top_val != nested_val:
            signals.append(f"top_level_mismatch_{ctx_key}")

    return {
        "propagation_signals": signals[:10],
        "propagation_coherent": len(signals) == 0,
        "canonical_governance": gov,
    }
