#!/usr/bin/env python3
"""
Force one raw post → minimal draft → optional publish (diagnostic).

Usage:
  python3 tools/force_single_draft.py
  python3 tools/force_single_draft.py --publish
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv()


async def _run(*, publish: bool) -> int:
    from app.config import load_settings
    from ai.openai_client import create_openai_client
    from app.telegram_bot import create_newsroom_bot
    from app.recovery.minimal_draft import try_minimal_draft_from_raw
    from app.recovery.pipeline_state_reconciler import reconcile_pipeline_state
    from db.repository import fetch_unprocessed_raw_posts
    from db.session import init_db, session_scope
    from scheduler.jobs import build_pipeline_context

    settings = load_settings()
    await init_db(settings.database_url)
    bot = create_newsroom_bot(settings)
    openai = create_openai_client(
        settings.openai_api_key,
        timeout=settings.openai_http_timeout_sec,
        max_retries=settings.openai_max_retries,
    )
    ctx = build_pipeline_context(settings, bot, openai, ai_pipeline_enabled=True)

    async with session_scope() as session:
        posts = await fetch_unprocessed_raw_posts(session, limit=1)
    if not posts:
        print("FORCE_DRAFT: no raw_unprocessed posts")
        return 1

    draft_id = await try_minimal_draft_from_raw(ctx, posts)
    if draft_id is None:
        print("FORCE_DRAFT: minimal path did not create draft (duplicate or empty body)")
        return 1

    print(f"FORCE_DRAFT: created draft_id={draft_id}")
    if not publish:
        return 0

    from publisher.publish_service import PublishFlowOutcome, execute_admin_publication_flow

    res = await execute_admin_publication_flow(
        bot,
        settings,
        draft_id,
        bypass_cadence=True,
        bypass_leadership=True,
    )
    if res.outcome is PublishFlowOutcome.OK:
        print(f"FORCE_PUBLISH: ok message_id={res.channel_message_id}")
        return 0
    print(f"FORCE_PUBLISH: {res.outcome.value} error={res.error}")
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="Force minimal raw→draft (optional publish)")
    p.add_argument("--publish", action="store_true", help="Also publish with bypass gates")
    args = p.parse_args()
    return asyncio.run(_run(publish=args.publish))


if __name__ == "__main__":
    raise SystemExit(main())
