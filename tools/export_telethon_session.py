#!/usr/bin/env python3
"""Export TELETHON_SESSION_STRING for production .env (run in Terminal.app)."""
from __future__ import annotations

import asyncio
import os
import sys


def _require(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"Missing env {name}. Example:", file=sys.stderr)
        print(f"  export {name}=...", file=sys.stderr)
        sys.exit(1)
    return val


async def _main() -> None:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    api_id = int(_require("TELEGRAM_API_ID"))
    api_hash = _require("TELEGRAM_API_HASH")

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()
    print("\n# Paste into /opt/newsroom/deploy/timeweb/.env\n")
    print("TELETHON_SESSION_STRING=" + client.session.save())
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(_main())
