"""Normalize DATABASE_URL for async SQLAlchemy and Alembic sync migrations."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine.url import URL, make_url


def _url_render(u: URL) -> str:
    """Stable string for URLs (SQLAlchemy 2 may redact passwords in ``str(URL)``)."""
    try:
        return u.render_as_string(hide_password=False)
    except Exception:
        return str(u)


def normalize_async_database_url(raw: str) -> str:
    """
    Ensure driver matches async stack:
    - sqlite / sqlite+aiosqlite → sqlite+aiosqlite
    - postgresql / postgres → postgresql+asyncpg
    - postgresql+psycopg2 / postgresql+psycopg → postgresql+asyncpg (app runtime)
    """
    u = make_url(raw.strip())
    name = u.drivername
    if name in ("sqlite", "aiosqlite"):
        return _url_render(u.set(drivername="sqlite+aiosqlite"))
    if name in ("postgres", "postgresql"):
        return _url_render(u.set(drivername="postgresql+asyncpg"))
    if name == "postgresql+psycopg2" or name == "postgresql+psycopg":
        return _url_render(u.set(drivername="postgresql+asyncpg"))
    if name == "postgresql+asyncpg":
        return _url_render(u)
    return raw.strip()


def database_backend_label(url: str) -> str:
    u = make_url(url)
    if u.get_backend_name() in ("sqlite", "aiosqlite"):
        return "sqlite"
    if "postgresql" in u.get_backend_name():
        return "postgresql"
    return u.get_backend_name()


def is_sqlite_async_url(url: str) -> bool:
    u = make_url(url)
    return u.get_backend_name() in ("sqlite", "aiosqlite")


def is_postgresql_async_url(url: str) -> bool:
    u = make_url(url)
    return "postgresql" in u.get_backend_name()


def sqlite_path_from_url(url: str) -> Path | None:
    """Filesystem path for sqlite+aiosqlite URLs, else None."""
    if not is_sqlite_async_url(url):
        return None
    u = make_url(url.strip())
    if not u.database:
        return None
    raw = str(u.database)
    if raw == ":memory:":
        return None
    return Path(raw).expanduser().resolve()


def alembic_sync_url_from_async(url: str) -> str:
    """Translate async app URL to synchronous migration URL (Alembic)."""
    u: URL = make_url(url.strip())
    if u.drivername in ("sqlite", "aiosqlite", "sqlite+aiosqlite"):
        return _url_render(u.set(drivername="sqlite"))
    if u.drivername == "postgresql+asyncpg":
        try:
            return _url_render(u.set(drivername="postgresql+psycopg"))
        except Exception:
            return _url_render(u.set(drivername="postgresql+psycopg2"))
    if u.drivername in ("postgresql+psycopg", "postgresql+psycopg2"):
        return _url_render(u)
    if u.drivername in ("postgres", "postgresql"):
        return _url_render(u.set(drivername="postgresql+psycopg"))
    return _url_render(u)
