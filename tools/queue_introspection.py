#!/usr/bin/env python3
"""Read-only queue, DLQ, and publish-lock introspection."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(description="Read-only queue introspection")
    p.add_argument("--json-output", default="")
    args = p.parse_args()

    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except ImportError:
        pass

    from app.config import load_settings
    from utils.queue_introspection import collect_queue_introspection

    settings = load_settings()
    report = asyncio.run(collect_queue_introspection(settings))
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.json_output:
        Path(args.json_output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
