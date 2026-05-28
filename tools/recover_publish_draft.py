#!/usr/bin/env python3
"""Retry publish for a failed draft using current transport (post-recovery validation)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


async def _run(draft_id: int, *, bypass_cadence: bool) -> int:
    from app.config import load_settings
    from app.telegram_bot import create_newsroom_bot
    from db.repository import reset_failed_draft_to_pending
    from db.session import session_scope
    from publisher.publish_service import PublishFlowOutcome, execute_admin_publication_flow

    settings = load_settings()
    from db.session import init_db

    await init_db(settings.database_url)
    bot = create_newsroom_bot(settings)
    try:
        async with session_scope() as session:
            await reset_failed_draft_to_pending(session, draft_id)
        res = await execute_admin_publication_flow(
            bot,
            settings,
            draft_id,
            bypass_cadence=bypass_cadence,
            bypass_leadership=True,
        )
        print(
            {
                "draft_id": draft_id,
                "outcome": res.outcome.value,
                "channel_message_id": res.channel_message_id,
                "error": res.error,
            }
        )
        return 0 if res.outcome == PublishFlowOutcome.OK else 1
    finally:
        await bot.session.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Recover publish for failed draft")
    p.add_argument("draft_id", type=int)
    p.add_argument("--bypass-cadence", action="store_true")
    args = p.parse_args()
    return asyncio.run(_run(args.draft_id, bypass_cadence=args.bypass_cadence))


if __name__ == "__main__":
    raise SystemExit(main())
