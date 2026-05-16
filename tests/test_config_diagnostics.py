from __future__ import annotations

from app.config_diagnostics import build_config_doctor_report, missing_env_for_bootstrap
from tests.conftest import minimal_test_settings


def test_missing_env_for_bootstrap_smoke() -> None:
    m = missing_env_for_bootstrap()
    assert isinstance(m, list)


def test_build_config_doctor_report_shape() -> None:
    s = minimal_test_settings()
    r = build_config_doctor_report(s)
    assert r.get("ok") is True
    assert "app_version" in r
    assert "safe_mode" in r
