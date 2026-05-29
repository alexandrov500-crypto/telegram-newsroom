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


async def _run(draft_id: int, *, bypass_cadence: bool, operator_override: bool = False) -> int:
    from app.config import load_settings
    from app.reliability.stuck_publishing_recovery import rollback_stale_publishing_draft
    from app.telegram_bot import create_newsroom_bot
    from db.models import DraftStatus
    from db.repository import get_draft_by_id, reopen_rejected_draft_to_pending, reset_failed_draft_to_pending
    from db.session import session_scope
    from publisher.publish_service import PublishFlowOutcome, execute_admin_publication_flow

    settings = load_settings()
    from db.session import init_db

    await init_db(settings.database_url)
    bot = create_newsroom_bot(settings)
    try:
        async with session_scope() as session:
            d = await get_draft_by_id(session, draft_id)
            if d is None:
                print({"draft_id": draft_id, "error": "missing"})
                return 1
            if d.status == DraftStatus.PUBLISHING.value:
                await rollback_stale_publishing_draft(session, draft_id, force=True)
            elif d.status == DraftStatus.FAILED.value:
                await reset_failed_draft_to_pending(session, draft_id)
            elif d.status == DraftStatus.REJECTED.value and operator_override:
                await reopen_rejected_draft_to_pending(session, draft_id)
        res = await execute_admin_publication_flow(
            bot,
            settings,
            draft_id,
            bypass_cadence=bypass_cadence,
            bypass_leadership=True,
            operator_override=operator_override,
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
    p.add_argument("--operator-override", action="store_true")
    args = p.parse_args()
    return asyncio.run(
        _run(
            args.draft_id,
            bypass_cadence=args.bypass_cadence,
            operator_override=args.operator_override,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
