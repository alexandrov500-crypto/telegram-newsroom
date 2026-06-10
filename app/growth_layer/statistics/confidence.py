"""Bootstrap confidence intervals."""

from __future__ import annotations

import random
from typing import Any


def bootstrap_confidence_interval(
    values: list[float],
    *,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> dict[str, float | None]:
    """95% bootstrap CI for the mean (default)."""
    if not values:
        return {"mean": None, "ci_low": None, "ci_high": None}
    if len(values) == 1:
        v = round(float(values[0]), 4)
        return {"mean": v, "ci_low": v, "ci_high": v}

    rng = random.Random(seed)
    n = len(values)
    boot_means: list[float] = []
    reps = max(100, int(n_bootstrap))
    for _ in range(reps):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        boot_means.append(sum(sample) / n)
    boot_means.sort()
    alpha = (1.0 - confidence) / 2.0
    lo_idx = max(0, int(alpha * len(boot_means)))
    hi_idx = min(len(boot_means) - 1, int((1.0 - alpha) * len(boot_means)))
    mean = sum(values) / n
    return {
        "mean": round(mean, 4),
        "ci_low": round(boot_means[lo_idx], 4),
        "ci_high": round(boot_means[hi_idx], 4),
    }
