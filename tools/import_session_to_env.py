#!/usr/bin/env python3
"""
Import TELETHON_SESSION_STRING into .env without re-login.

Usage (if you already have the line from a previous gen_session run):
  python tools/import_session_to_env.py --file ~/session_line.txt
  # file contains one line: TELETHON_SESSION_STRING=1BVts...

Or paste value only:
  python tools/import_session_to_env.py --value '1BVtsOHwBu...'
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gen_session import ENV_PATH, _write_session_to_env  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", type=Path, help="File with TELETHON_SESSION_STRING=... line")
    g.add_argument("--value", help="Session string without key prefix")
    args = p.parse_args()

    if args.file:
        raw = args.file.read_text(encoding="utf-8").strip()
    else:
        raw = args.value.strip()
        if not raw.startswith("TELETHON_SESSION_STRING="):
            raw = f"TELETHON_SESSION_STRING={raw}"

    _write_session_to_env(raw)
    print("Done. Run: python gen_session.py --verify")


if __name__ == "__main__":
    main()
