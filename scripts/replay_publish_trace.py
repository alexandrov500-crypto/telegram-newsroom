#!/usr/bin/env python3
"""Read-only forensic replay of a publish (does NOT republish to Telegram)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.config import bootstrap_env
from bot.ops_forensics.replay import replay_publish_forensics


def main() -> int:
    bootstrap_env()
    p = argparse.ArgumentParser(description="Forensic publish replay (read-only)")
    p.add_argument("--id", type=int, required=True, help="pending_news_id / publish_id")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    report = replay_publish_forensics(args.id)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print("=" * 56)
        print(f" FORENSIC REPLAY (read-only) — publish_id={args.id}")
        print("=" * 56)
        print(f"  correlation_id: {report.get('correlation_id')}")
        print(f"  mode: {(report.get('publish_trace') or {}).get('mode')}")
        print(f"  published: {(report.get('publish_trace') or {}).get('published')}")
        print(f"  guard: {(report.get('publish_trace') or {}).get('guard_result')}")
        print(f"  timeline events: {len(report.get('timeline_events') or [])}")
        print(f"  audit entries: {len(report.get('audit_log') or [])}")
        print("\n  source_input:")
        print(json.dumps(report.get("source_input"), indent=2)[:1200])
        print("\n  NOTE:", report.get("telegram_payload_note"))
        print("=" * 56)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
