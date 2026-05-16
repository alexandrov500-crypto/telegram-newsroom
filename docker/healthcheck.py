#!/usr/bin/env python3
"""Container healthcheck: validate env, DB reachability (no Telegram/OpenAI)."""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text


async def _main() -> None:
    from app.config import load_settings
    from app.startup_validation import validate_settings_for_launch
    from db.session import close_db, get_engine, init_db

    settings = load_settings()
    validate_settings_for_launch(settings)
    await init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
    engine = get_engine()
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    await close_db()


async def _readiness() -> None:
    from app.config import load_settings
    from app.startup_validation import validate_settings_for_launch
    from db.session import close_db, init_db
    from utils.redis_client import close_redis, init_redis_from_settings
    from utils.runtime_health import gather_runtime_health
    from worker.job_queue import close_job_queue, init_job_queue

    settings = load_settings()
    validate_settings_for_launch(settings)
    await init_db(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
    await init_redis_from_settings(settings)
    await init_job_queue(settings)
    try:
        snap = await gather_runtime_health(settings, include_openai=False)
        if not snap.get("ok"):
            raise RuntimeError(snap)
    finally:
        await close_job_queue()
        await close_redis()
        await close_db()


if __name__ == "__main__":
    try:
        if "--readiness" in sys.argv:
            asyncio.run(_readiness())
        else:
            asyncio.run(_main())
    except Exception as exc:
        print(f"healthcheck failed: {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)
