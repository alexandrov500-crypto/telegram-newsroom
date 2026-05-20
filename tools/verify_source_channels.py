#!/usr/bin/env python3
"""Verify SOURCE_CHANNELS are readable with current Telethon session (no secrets printed)."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def _main() -> int:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env", override=True)

    session = os.getenv("TELETHON_SESSION_STRING", "").strip()
    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()
    raw = os.getenv("SOURCE_CHANNELS", "").strip()

    if not session:
        print("FAIL: TELETHON_SESSION_STRING empty — run: python gen_session.py --write-env", file=sys.stderr)
        return 1
    if not raw:
        print("FAIL: SOURCE_CHANNELS empty — add @channel1,@channel2 to .env", file=sys.stderr)
        return 1

    channels = [c.strip() for c in raw.split(",") if c.strip()]
    if not channels:
        print("FAIL: SOURCE_CHANNELS has no entries", file=sys.stderr)
        return 1

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(session), int(api_id), api_hash)
    ok = 0
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("FAIL: Telethon session not authorized", file=sys.stderr)
            return 1
        for ch in channels:
            try:
                ent = await client.get_entity(ch)
                title = getattr(ent, "title", None) or getattr(ent, "username", ch)
                print(f"OK  {ch} → {title}")
                ok += 1
            except Exception as exc:
                print(f"FAIL {ch} → {exc.__class__.__name__}: {exc}", file=sys.stderr)
    finally:
        await client.disconnect()

    if ok != len(channels):
        print(f"\nFAIL: {ok}/{len(channels)} channels readable", file=sys.stderr)
        return 1
    print(f"\nPASS: all {ok} source channel(s) readable")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
