#!/usr/bin/env python3
"""Read-only staging environment verification (no Telegram API calls)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

_PLACEHOLDER_MARKERS = (
    "your_api_hash",
    "replace_with",
    "123456789:replace",
    "test-session",
    "12345678",
)


def _masked(val: str) -> str:
    v = (val or "").strip()
    if len(v) <= 4:
        return "(empty)"
    return f"{v[:2]}…{v[-2:]} (len={len(v)})"


def _looks_placeholder(val: str) -> bool:
    low = (val or "").lower()
    return not low or any(m in low for m in _PLACEHOLDER_MARKERS)


def _check_env() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    required = (
        "TELEGRAM_API_ID",
        "TELEGRAM_API_HASH",
        "BOT_TOKEN",
        "ADMIN_USER_ID",
        "TARGET_CHANNEL_ID",
    )
    for key in required:
        raw = os.environ.get(key, "")
        if not raw.strip():
            rows.append({"check": key, "status": "MISSING", "detail": "not set"})
        elif _looks_placeholder(raw):
            rows.append({"check": key, "status": "PLACEHOLDER", "detail": _masked(raw)})
        else:
            rows.append({"check": key, "status": "OK", "detail": _masked(raw)})

    sess = os.environ.get("TELETHON_SESSION_STRING", "").strip()
    path = os.environ.get("TELETHON_SESSION_PATH", "").strip()
    if path:
        p = Path(path)
        rows.append(
            {
                "check": "TELETHON_SESSION_PATH",
                "status": "OK" if p.exists() else "MISSING_FILE",
                "detail": str(p),
            }
        )
    elif sess and not _looks_placeholder(sess):
        rows.append({"check": "TELETHON_SESSION_STRING", "status": "OK", "detail": _masked(sess)})
    else:
        rows.append({"check": "TELETHON_SESSION", "status": "MISSING", "detail": "set STRING or PATH"})

    dry = os.environ.get("DRY_RUN", "false").lower()
    rows.append({"check": "DRY_RUN", "status": "INFO", "detail": dry})
    return rows


async def _check_redis() -> dict[str, str]:
    try:
        from utils.redis_client import get_redis

        r = await get_redis()
        if r is None:
            return {"status": "DISABLED", "detail": "REDIS_ENABLED false or no client"}
        await r.ping()
        return {"status": "OK", "detail": "PING"}
    except Exception as exc:
        return {"status": "FAIL", "detail": repr(exc)}


def run_verify() -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    env_rows = _check_env()
    for row in env_rows:
        if row["status"] in {"MISSING", "PLACEHOLDER", "MISSING_FILE"}:
            findings.append(
                {
                    "severity": "HIGH",
                    "code": f"env_{row['check']}",
                    "message": f"{row['check']}: {row['status']}",
                    "remediation": "Configure staging .env before live validation",
                }
            )

    redis_status: dict[str, str] = {"status": "SKIPPED", "detail": ""}
    try:
        import asyncio

        redis_status = asyncio.run(_check_redis())
        if redis_status["status"] == "FAIL":
            findings.append(
                {
                    "severity": "MEDIUM",
                    "code": "redis_ping",
                    "message": redis_status["detail"],
                    "remediation": "Fix REDIS_URL or disable REDIS_ENABLED for T1",
                }
            )
    except Exception as exc:
        redis_status = {"status": "ERROR", "detail": repr(exc)}

    diag_status = "SKIPPED"
    try:
        from tools.live_telegram_diagnostics import run_diagnostics

        diag = run_diagnostics()
        diag_status = str(diag.get("status", ""))
        if diag_status == "FAIL":
            findings.append(
                {
                    "severity": "HIGH",
                    "code": "diagnostics_fail",
                    "message": "live_telegram_diagnostics FAIL",
                    "remediation": "Resolve diagnostics findings before live publish",
                }
            )
    except Exception as exc:
        diag_status = f"ERROR: {exc}"

    dry_run = os.environ.get("DRY_RUN", "").lower() in {"1", "true", "yes"}
    if not dry_run and any(r["check"] == "TARGET_CHANNEL_ID" and r["status"] == "OK" for r in env_rows):
        findings.append(
            {
                "severity": "MEDIUM",
                "code": "dry_run_off",
                "message": "DRY_RUN is not enabled",
                "remediation": "Use DRY_RUN=true for T0 staging; enable publish only for bounded sign-off",
            }
        )

    worst = max({"LOW": 1, "MEDIUM": 2, "HIGH": 3}.get(f["severity"], 0) for f in findings) if findings else 0
    status = "FAIL" if worst >= 3 else ("WARNING" if findings else "OK")

    return {
        "schema_version": 1,
        "read_only": True,
        "no_telegram_api_calls": True,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": status,
        "env_checks": env_rows,
        "redis": redis_status,
        "diagnostics_status": diag_status,
        "findings": findings,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--json-output", default="")
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO / ".env")
    except ImportError:
        pass
    report = run_verify()
    if args.json_output:
        Path(args.json_output).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, indent=2))
    # Exit 1 only on explicit --strict with FAIL; CI uses tests without strict.
    if args.strict and report.get("status") == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
