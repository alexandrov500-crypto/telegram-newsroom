#!/usr/bin/env python3
"""Validate .env for production-lite + VPS deploy (no secret values printed)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"

REQUIRED = (
    "OPENAI_API_KEY",
    "BOT_TOKEN",
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "TELETHON_SESSION_STRING",
    "ADMIN_USER_ID",
    "TARGET_CHANNEL_ID",
    "SOURCE_CHANNELS",
    "APP_DEPLOYMENT_PROFILE",
)


def main() -> int:
    try:
        from dotenv import load_dotenv
    except ImportError:
        print("FAIL: pip install python-dotenv", file=sys.stderr)
        return 1

    if not ENV_PATH.is_file():
        print(f"FAIL: missing {ENV_PATH}", file=sys.stderr)
        return 1

    load_dotenv(ENV_PATH, override=True)  # .env wins over stale shell exports
    errors: list[str] = []

    for key in REQUIRED:
        val = os.getenv(key, "").strip()
        if not val or "replace" in val.lower():
            errors.append(f"{key} missing or placeholder")
            continue
        print(f"OK  {key} (len={len(val)})")

    api_id = os.getenv("TELEGRAM_API_ID", "").strip()
    if api_id and not api_id.isdigit():
        errors.append("TELEGRAM_API_ID must be digits only")

    channels = os.getenv("SOURCE_CHANNELS", "")
    if channels and "@" not in channels and not channels.strip().startswith("-100"):
        errors.append("SOURCE_CHANNELS should use @username or -100... ids")

    if errors:
        print("\nFAIL:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("\nPASS: production env structure looks ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
