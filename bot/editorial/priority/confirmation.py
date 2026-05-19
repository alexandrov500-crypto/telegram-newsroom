from __future__ import annotations

from collections.abc import Sequence

_TRUSTED_WIRES = frozenset(
    {"ap", "reuters", "bloomberg", "afp", "bbc", "associated press", "financial times", "ft"},
)


def cross_source_confirmation_score(
    *,
    source: str | None,
    source_count: int,
    variant_count: int,
    sources: Sequence[str] | None = None,
    source_trust: float,
) -> tuple[float, int]:
    """Higher when multiple trusted outlets corroborate."""
    names = {str(s).strip().lower() for s in (sources or ()) if s}
    if source:
        names.add(source.strip().lower())
    trusted_hits = sum(1 for n in names if n in _TRUSTED_WIRES or any(w in n for w in _TRUSTED_WIRES))
    count = max(source_count, len(names), variant_count)
    if count <= 1:
        base = 0.35 if source_trust >= 0.7 else 0.22
        if trusted_hits:
            base += 0.12
        return round(min(0.55, base), 3), count
    corroboration = min(1.0, (count - 1) / 3.0)
    trust_boost = min(0.25, trusted_hits * 0.1)
    score = min(1.0, 0.45 + corroboration * 0.4 + trust_boost + source_trust * 0.15)
    return round(score, 3), count
