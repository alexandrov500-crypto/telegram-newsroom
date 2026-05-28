#!/usr/bin/env python3
"""Bot responsiveness checks (health HTTP + optional Telegram getMe)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    port = int(os.getenv("HEALTH_HTTP_PORT", "8080") or 0)
    issues: list[str] = []
    report: dict[str, object] = {}

    if port > 0:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=4) as resp:
                health = json.loads(resp.read().decode())
            report["http_health"] = health.get("status")
            tg = (health.get("dependencies") or {}).get("telegram_api") or {}
            report["polling_active"] = tg.get("polling_active")
            report["bot_username"] = tg.get("bot_username")
            if not health.get("startup_complete"):
                issues.append("startup_complete=false")
            if tg.get("polling_active") is False:
                issues.append("polling_active=false")
        except urllib.error.URLError as exc:
            issues.append(f"/health unreachable: {exc}")
    else:
        issues.append("HEALTH_HTTP_PORT not set")

    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    if token:
        try:
            req = urllib.request.Request(
                f"https://api.telegram.org/bot{token}/getMe",
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            report["telegram_getMe"] = data.get("ok")
            if not data.get("ok"):
                issues.append("telegram getMe failed")
        except Exception as exc:
            issues.append(f"telegram getMe: {exc}")
    else:
        issues.append("BOT_TOKEN missing")

    report["issues"] = issues
    report["ok"] = not issues
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
