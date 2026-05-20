#!/usr/bin/env python3
"""List Telegram channels/groups your Telethon session can see (pick SOURCE_CHANNELS)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def _main() -> int:
    from dotenv import load_dotenv
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.types import Channel

    load_dotenv(ROOT / ".env", override=True)
    session = os.getenv("TELETHON_SESSION_STRING", "").strip()
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    if not session:
        print("FAIL: TELETHON_SESSION_STRING empty", file=sys.stderr)
        return 1

    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("FAIL: session not authorized — run: python gen_session.py --write-env", file=sys.stderr)
        return 1

    print("Channels/groups you can use in SOURCE_CHANNELS:\n")
    print(f"{'REF':<28} {'TITLE':<40} ID")
    print("-" * 80)
    count = 0
    async for dialog in client.iter_dialogs():
        ent = dialog.entity
        if not isinstance(ent, Channel):
            continue
        ref = f"@{ent.username}" if ent.username else str(dialog.id)
        title = (dialog.title or "")[:38]
        print(f"{ref:<28} {title:<40} {dialog.id}")
        count += 1
        if count >= 40:
            print("... (truncated at 40 — narrow search in Telegram if needed)")
            break

    print("\nExample .env line:")
    print("SOURCE_CHANNELS=@channel1,@channel2")
    print("# or mix: SOURCE_CHANNELS=-1001234567890,@publicname")
    await client.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
