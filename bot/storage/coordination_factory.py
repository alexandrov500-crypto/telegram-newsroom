from __future__ import annotations

import os
from pathlib import Path

from bot.storage.coordination_repository import CoordinationRepository
from utils.database_url import is_postgresql_async_url


def create_coordination_repository(db_path: Path) -> CoordinationRepository:
    """Shared cluster state: SQLite file (dev) or PostgreSQL (production)."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url and is_postgresql_async_url(url):
        return CoordinationRepository(database_url=url)
    return CoordinationRepository(db_path)


def coordination_database_label(db_path: Path) -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if url and is_postgresql_async_url(url):
        return "postgresql"
    return str(db_path)
