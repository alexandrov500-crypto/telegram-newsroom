from __future__ import annotations

from app.versioning import APP_VERSION, public_metadata


def test_public_metadata_keys() -> None:
    m = public_metadata()
    assert m["app_version"] == APP_VERSION
    assert "runtime_state_schema_version" in m
