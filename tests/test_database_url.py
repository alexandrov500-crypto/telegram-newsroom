from __future__ import annotations

from utils.database_url import (
    alembic_sync_url_from_async,
    database_backend_label,
    is_postgresql_async_url,
    is_sqlite_async_url,
    normalize_async_database_url,
)


def test_normalize_sqlite_file_url() -> None:
    u = normalize_async_database_url("sqlite:///./newsroom.db")
    assert "sqlite+aiosqlite" in u


def test_normalize_postgresql_defaults_asyncpg() -> None:
    u = normalize_async_database_url("postgresql://user:pass@localhost:5432/db")
    assert "postgresql+asyncpg" in u


def test_normalize_asyncpg_passthrough() -> None:
    from sqlalchemy.engine.url import make_url

    raw = "postgresql+asyncpg://user:pass@localhost:5432/db"
    out = normalize_async_database_url(raw)
    u1 = make_url(raw)
    u2 = make_url(out)
    assert u2.drivername == "postgresql+asyncpg"
    assert u1.username == u2.username and (u1.password or "") == (u2.password or "")
    assert (u1.host or "") == (u2.host or "") and str(u1.database) == str(u2.database)


def test_alembic_sync_maps_asyncpg() -> None:
    sync_url = alembic_sync_url_from_async("postgresql+asyncpg://user:pass@localhost:5432/db")
    assert "postgresql+" in sync_url
    assert "asyncpg" not in sync_url


def test_backend_labels() -> None:
    assert database_backend_label("sqlite+aiosqlite:///:memory:") == "sqlite"
    assert is_sqlite_async_url("sqlite+aiosqlite:///:memory:")
    u = normalize_async_database_url("postgresql://u:p@h/db")
    assert is_postgresql_async_url(u)
