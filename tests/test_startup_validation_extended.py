from __future__ import annotations

from pathlib import Path

import pytest

from app.startup_validation import validate_settings_for_launch
from tests.conftest import minimal_test_settings


def test_sqlite_database_parent_directory_must_exist(tmp_path: Path):
    (tmp_path / "nodir").mkdir()
    url = f"sqlite+aiosqlite:///{tmp_path / 'nodir' / 'missing_sub' / 'db.sqlite'}"
    s = minimal_test_settings(database_url=url)
    with pytest.raises(RuntimeError, match="directory does not exist"):
        validate_settings_for_launch(s)


def test_openai_timeouts_must_be_ordered():
    s = minimal_test_settings(openai_request_timeout_sec=500.0, openai_http_timeout_sec=30.0)
    with pytest.raises(RuntimeError, match="OPENAI_REQUEST_TIMEOUT_SEC"):
        validate_settings_for_launch(s)


def test_channel_collect_delay_cap():
    s = minimal_test_settings(channel_collect_delay_seconds=130.0)
    with pytest.raises(RuntimeError, match="CHANNEL_COLLECT_DELAY"):
        validate_settings_for_launch(s)


def test_telethon_session_parent_must_exist(tmp_path: Path):
    s = minimal_test_settings(telethon_session_path=str(tmp_path / "no_parent_dir" / "s.session"))
    with pytest.raises(RuntimeError, match="TELETHON_SESSION_PATH parent"):
        validate_settings_for_launch(s)


def test_invalid_database_url_rejected():
    s = minimal_test_settings(database_url="%%%not_a_sqlalchemy_url%%%")
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_settings_for_launch(s)
