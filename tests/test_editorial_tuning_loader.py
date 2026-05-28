from __future__ import annotations

from app.editorial.tuning_loader import get_editorial_tuning, load_editorial_tuning


def test_default_tuning_no_cta() -> None:
    t = load_editorial_tuning(reload=True)
    assert t.structure.include_cta is False
    assert t.attribution.style == "source"
    assert t.quality_gate.mode == "log_only"


def test_get_editorial_tuning_cached() -> None:
    a = get_editorial_tuning()
    b = get_editorial_tuning()
    assert a.structure.headline_max_chars == b.structure.headline_max_chars
