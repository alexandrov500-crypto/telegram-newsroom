#!/usr/bin/env python3
"""
Generate TELETHON_SESSION_STRING for production (run once on a trusted machine).

Usage:
  python gen_session.py              # interactive login → print session line
  python gen_session.py --write-env  # also update .env (local only, never commit)
  python gen_session.py --verify     # test existing TELETHON_SESSION_STRING in .env
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as exc:
        print("Missing package: python-dotenv. Run: pip install python-dotenv", file=sys.stderr)
        raise SystemExit(1) from exc
    if ENV_PATH.is_file():
        # override=True: project .env wins over stale shell exports (e.g. TELEGRAM_API_ID=ВАШ_ID)
        load_dotenv(ENV_PATH, override=True)
    else:
        print(f"Warning: {ENV_PATH} not found — using environment variables only.", file=sys.stderr)


def _require_api_credentials() -> tuple[int, str]:
    api_id_raw = os.getenv("TELEGRAM_API_ID", "").strip()
    api_hash = os.getenv("TELEGRAM_API_HASH", "").strip()

    if not api_id_raw:
        print(
            "TELEGRAM_API_ID is empty.\n"
            "Add it to .env from https://my.telegram.org/apps (digits only).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not api_hash or "replace" in api_hash.lower():
        print(
            "TELEGRAM_API_HASH is empty or still a placeholder.\n"
            "Add the real hash from https://my.telegram.org/apps to .env.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    try:
        api_id = int(api_id_raw)
    except ValueError:
        print("TELEGRAM_API_ID must be an integer (digits only).", file=sys.stderr)
        print(f"  Current value looks invalid (len={len(api_id_raw)}).", file=sys.stderr)
        if ENV_PATH.is_file():
            print(f"  Loaded from: {ENV_PATH}", file=sys.stderr)
        print(
            "  If you previously ran: export TELEGRAM_API_ID=ВАШ_ID — run:\n"
            "    unset TELEGRAM_API_ID TELEGRAM_API_HASH",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return api_id, api_hash


def _session_len_on_disk() -> int:
    if not ENV_PATH.is_file():
        return 0
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("TELETHON_SESSION_STRING="):
            return len(line.split("=", 1)[1])
    return 0


def _masked_session_preview(value: str) -> str:
    if len(value) < 16:
        return "(too short)"
    return f"{value[:8]}...{value[-8:]} (len={len(value)})"


def _write_session_to_env(session_line: str) -> None:
    """Atomically update TELETHON_SESSION_STRING= in .env; verify on disk."""
    if not ENV_PATH.is_file():
        print(f"Cannot write: {ENV_PATH} missing", file=sys.stderr)
        raise SystemExit(1)
    key, _, value = session_line.partition("=")
    if key != "TELETHON_SESSION_STRING" or not value:
        print("Invalid session line format.", file=sys.stderr)
        raise SystemExit(1)
    if len(value) < 100:
        print(f"Session string too short (len={len(value)}). Login may have failed.", file=sys.stderr)
        raise SystemExit(1)

    text = ENV_PATH.read_text(encoding="utf-8")
    # Remove ALL duplicate TELETHON_SESSION_STRING lines, then insert one canonical line.
    lines = [ln for ln in text.splitlines() if not ln.startswith("TELETHON_SESSION_STRING=")]
    new_line = f"TELETHON_SESSION_STRING={value}"
    insert_at = len(lines)
    for i, ln in enumerate(lines):
        if ln.startswith("TELEGRAM_API_HASH="):
            insert_at = i + 1
            break
    lines.insert(insert_at, new_line)
    out = "\n".join(lines).rstrip("\n") + "\n"

    tmp = ENV_PATH.with_suffix(".env.tmp")
    tmp.write_text(out, encoding="utf-8")
    os.replace(tmp, ENV_PATH)
    try:
        os.chmod(ENV_PATH, 0o600)
    except OSError as exc:
        print(f"Warning: chmod .env failed: {exc}", file=sys.stderr)

    written = _session_len_on_disk()
    if written < 100:
        print(
            f"FAIL: .env on disk still has empty/short session (len={written}).\n"
            f"  Path: {ENV_PATH.resolve()}\n"
            "  If Cursor has .env open: close tab or File → Revert File — do not save stale buffer over disk.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    print(f"Updated {ENV_PATH.resolve()}")
    print(f"TELETHON_SESSION_STRING on disk: {_masked_session_preview(value)}")
    print("If .env is open in the editor: reload from disk (do not overwrite with old empty line).")


async def _generate_session(*, write_env: bool) -> None:
    from telethon import TelegramClient
    from telethon.errors import (
        ApiIdInvalidError,
        PhoneNumberInvalidError,
        SessionPasswordNeededError,
    )
    from telethon.sessions import StringSession

    api_id, api_hash = _require_api_credentials()

    print("Starting Telethon login (production StringSession)...")
    print("You will be asked for:")
    print("  1) phone number  (+79... international format)")
    print("  2) code from Telegram app")
    print("  3) Cloud Password if 2FA is enabled on your account")
    print()

    client = TelegramClient(StringSession(), api_id, api_hash)
    try:
        await client.start()
        me = await client.get_me()
        session_string = client.session.save()
        line = f"TELETHON_SESSION_STRING={session_string}"
        print("\n--- Success ---")
        print(f"Logged in as: {me.first_name or ''} (id={me.id})")
        if write_env:
            _write_session_to_env(line)
        else:
            print("\nCopy this line into .env (and VPS deploy/timeweb/.env):\n")
            print(line)
            print("\nOr re-run with: python gen_session.py --write-env")
    except ApiIdInvalidError:
        print("Invalid TELEGRAM_API_ID / TELEGRAM_API_HASH. Check https://my.telegram.org/apps", file=sys.stderr)
        raise SystemExit(1)
    except PhoneNumberInvalidError:
        print("Invalid phone number. Use international format, e.g. +79001234567", file=sys.stderr)
        raise SystemExit(1)
    except SessionPasswordNeededError:
        print(
            "2FA password required. Re-run; Telethon will prompt for your Cloud Password.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"Login failed: {exc.__class__.__name__}", file=sys.stderr)
        raise SystemExit(1) from exc
    finally:
        await client.disconnect()


async def _verify_session() -> None:
    from telethon import TelegramClient
    from telethon.errors import AuthKeyUnregisteredError
    from telethon.sessions import StringSession

    api_id, api_hash = _require_api_credentials()
    session_string = os.getenv("TELETHON_SESSION_STRING", "").strip()
    if not session_string:
        print("TELETHON_SESSION_STRING is empty in .env. Run: python gen_session.py", file=sys.stderr)
        raise SystemExit(1)

    client = TelegramClient(StringSession(session_string), api_id, api_hash)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            print("Session is NOT authorized. Re-run: python gen_session.py", file=sys.stderr)
            raise SystemExit(1)
        me = await client.get_me()
        print(f"Telegram OK: authorized as id={me.id} username={me.username or '(none)'}")
    except AuthKeyUnregisteredError:
        print("Session expired or invalid. Re-run: python gen_session.py", file=sys.stderr)
        raise SystemExit(1)
    finally:
        await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate or verify Telethon StringSession for newsroom.")
    parser.add_argument(
        "--write-env",
        action="store_true",
        help="Write TELETHON_SESSION_STRING into .env (local machine only).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing TELETHON_SESSION_STRING in .env (no login).",
    )
    args = parser.parse_args()

    _load_env()

    if args.verify:
        asyncio.run(_verify_session())
    else:
        asyncio.run(_generate_session(write_env=args.write_env))


if __name__ == "__main__":
    main()
