#!/usr/bin/env python3
"""Find duplicate keys in .env and compare shell vs file (no secrets printed)."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
KEYS = ("TELEGRAM_API_ID", "TELEGRAM_API_HASH", "TELETHON_SESSION_STRING", "SOURCE_CHANNELS")


def _mask(val: str) -> str:
    v = (val or "").strip()
    if not v:
        return "EMPTY"
    if v.isdigit():
        return f"digits len={len(v)}"
    if all(c in "abcdef0123456789" for c in v.lower()):
        return f"hash len={len(v)}"
    return f"text repr={v[:12]!r}..."


def _scan_file() -> None:
    if not ENV_PATH.is_file():
        print(f"MISSING {ENV_PATH}")
        return
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines()
    found: dict[str, list[tuple[int, str]]] = {k: [] for k in KEYS}
    for i, line in enumerate(lines, start=1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        for k in KEYS:
            if s.startswith(f"{k}="):
                found[k].append((i, s.split("=", 1)[1]))
    print(f"=== {ENV_PATH} ===")
    for k in KEYS:
        entries = found[k]
        if not entries:
            print(f"  {k}: (not in file)")
            continue
        for ln, val in entries:
            print(f"  line {ln}: {k} → {_mask(val)}")
        if len(entries) > 1:
            print(f"  ** DUPLICATE {k} ({len(entries)} lines) — keep one, delete placeholders **")


def main() -> int:
    _scan_file()
    print("\n=== shell (before load_dotenv) ===")
    for k in KEYS:
        print(f"  {k}: {_mask(os.environ.get(k, ''))}")

    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    print("\n=== after load_dotenv(.env, override=True) ===")
    for k in KEYS:
        print(f"  {k}: {_mask(os.getenv(k, ''))}")

    api = os.getenv("TELEGRAM_API_ID", "").strip()
    try:
        int(api)
        print("\nTELEGRAM_API_ID int parse: STATUS OK")
        return 0
    except ValueError:
        print(f"\nTELEGRAM_API_ID int parse: FAIL ({_mask(api)})")
        print("Fix: unset TELEGRAM_API_ID TELEGRAM_API_HASH  OR remove duplicate/placeholder lines in .env")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
