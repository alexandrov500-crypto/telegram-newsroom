"""Two-sample significance tests with automatic test selection."""

from __future__ import annotations

import math
from typing import Any

try:
    from scipy import stats as scipy_stats
except ImportError:  # pragma: no cover - exercised via lazy import guard in tests
    scipy_stats = None  # type: ignore[assignment]


def _shapiro_normal(sample: list[float]) -> bool:
    if scipy_stats is None:
        return False
    n = len(sample)
    if n < 3 or n > 5000:
        return False
    try:
        _, p = scipy_stats.shapiro(sample)
        return float(p) > 0.05
    except Exception:
        return False


def _choose_test(sample_a: list[float], sample_b: list[float]) -> str:
    n_a, n_b = len(sample_a), len(sample_b)
    if n_a < 8 or n_b < 8:
        return "mannwhitneyu"
    if _shapiro_normal(sample_a) and _shapiro_normal(sample_b):
        return "ttest_ind"
    return "mannwhitneyu"


def compare_two_samples(
    sample_a: list[float],
    sample_b: list[float],
    *,
    alternative: str = "two-sided",
) -> dict[str, Any]:
    """
    Compare two independent samples.
    Uses Welch t-test when both samples look normal (n>=8); otherwise Mann-Whitney U.
    """
    warnings: list[str] = []
    n_a, n_b = len(sample_a), len(sample_b)
    if n_a < 30 or n_b < 30:
        warnings.append("small_sample_size")

    if n_a < 2 or n_b < 2:
        return {
            "p_value": None,
            "statistic": None,
            "test": "insufficient_data",
            "warnings": warnings,
        }

    if scipy_stats is None:
        return {
            "p_value": None,
            "statistic": None,
            "test": "scipy_unavailable",
            "warnings": warnings + ["scipy_unavailable"],
        }

    test = _choose_test(sample_a, sample_b)
    try:
        if test == "ttest_ind":
            stat, p = scipy_stats.ttest_ind(sample_a, sample_b, equal_var=False, alternative=alternative)
        else:
            stat, p = scipy_stats.mannwhitneyu(sample_a, sample_b, alternative=alternative)
        p_f = float(p)
        if math.isnan(p_f):
            p_f = None
        return {
            "p_value": round(p_f, 6) if p_f is not None else None,
            "statistic": round(float(stat), 4) if stat is not None and not math.isnan(float(stat)) else None,
            "test": test,
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "p_value": None,
            "statistic": None,
            "test": test,
            "warnings": warnings + [f"test_failed:{type(exc).__name__}"],
        }
