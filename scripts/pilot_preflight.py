#!/usr/bin/env python3
"""Pre-live checklist for controlled public pilot (canary mode)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def load_env_file(path: Path, *, override: bool = True) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        key = k.strip()
        val = v.strip().strip('"')
        if override:
            os.environ[key] = val
        else:
            os.environ.setdefault(key, val)


def sync_channel_env() -> None:
    pub = os.getenv("LIVE_PUBLIC_CHANNEL_ID")
    if pub:
        os.environ.setdefault("TELEGRAM_CHANNEL_ID", pub)
    ops = os.getenv("LIVE_OPS_CHANNEL_ID")
    if ops:
        os.environ.setdefault("TELEGRAM_OPERATOR_CHAT_ID", ops)
    shadow = os.getenv("LIVE_SHADOW_CHANNEL_ID")
    if shadow:
        os.environ.setdefault("TELEGRAM_DIGEST_CHANNEL_ID", shadow)


async def main_async(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    sync_channel_env()

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    from bot.live_ops.pilot_readiness import evaluate_pilot_db, evaluate_pilot_env
    from bot.live_ops.telegram_pilot import (
        PilotPreflightReport,
        authenticate_bot,
        send_test_messages,
        simulate_operational_commands,
        validate_public_channel,
        validate_send_channel,
    )
    from bot.storage.db import default_db_path, init_database

    report = PilotPreflightReport()
    results: dict = {}

    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or ""
    if not token:
        report.add("BOT_TOKEN valid", False, "BOT_TOKEN / TELEGRAM_BOT_TOKEN missing")
    else:
        try:
            me = await authenticate_bot(token)
            report.add("BOT_TOKEN valid", True, f"@{me.username} id={me.id}")
            results["bot"] = {"username": me.username, "id": me.id}
        except RuntimeError as exc:
            report.add("BOT_TOKEN valid", False, str(exc))

    env_report = evaluate_pilot_env()
    for c in env_report.checks:
        label_map = {
            "controlled_live_enabled": "Controlled live enabled",
            "live_mode_canary": "LIVE_MODE=canary",
            "public_channel": "Public channel ID configured",
            "ops_channel": "Ops channel ID configured",
            "bot_token": "BOT_TOKEN configured",
            "not_global_shadow": "SHADOW_PUBLISH_ONLY=false for canary",
        }
        label = label_map.get(c.name, c.name)
        report.add(label, c.passed, c.detail if not c.passed else "")

    pub = os.getenv("LIVE_PUBLIC_CHANNEL_ID") or os.getenv("TELEGRAM_CHANNEL_ID")
    ops = os.getenv("LIVE_OPS_CHANNEL_ID") or os.getenv("TELEGRAM_OPERATOR_CHAT_ID")
    shadow = os.getenv("LIVE_SHADOW_CHANNEL_ID") or os.getenv("TELEGRAM_DIGEST_CHANNEL_ID")

    token_ok = any(ln.label == "BOT_TOKEN valid" and ln.ok for ln in report.lines)
    bot: Bot | None = None
    if token and token_ok:
        bot = Bot(token=token, default=DefaultBotProperties())
        try:
            if pub:
                report.lines.append(await validate_public_channel(bot, int(pub)))
            else:
                report.add(
                    "Public channel accessible (post/edit/delete/media)",
                    False,
                    "LIVE_PUBLIC_CHANNEL_ID unset",
                )

            if ops:
                report.lines.append(
                    await validate_send_channel(
                        bot,
                        int(ops),
                        label="Ops channel accessible",
                        probe_send=True,
                    ),
                )
            else:
                report.add("Ops channel accessible", False, "LIVE_OPS_CHANNEL_ID unset")

            if shadow:
                report.lines.append(
                    await validate_send_channel(
                        bot,
                        int(shadow),
                        label="Shadow channel accessible",
                        probe_send=True,
                    ),
                )
            else:
                report.add("Shadow channel (optional)", True, "not configured")

            if args.send_test_message and ops:
                for tl in await send_test_messages(
                    bot,
                    ops_channel_id=int(ops),
                    shadow_channel_id=int(shadow) if shadow else None,
                ):
                    report.lines.append(tl)
        finally:
            await bot.session.close()
    elif token and not token_ok:
        report.add("Telegram channel checks", False, "skipped — invalid token")

    db_path = args.db or default_db_path()
    init_database(db_path)
    db_report = evaluate_pilot_db(db_path)
    report.add(
        "SQLite migrations applied",
        db_report.ready,
        "missing tables" if not db_report.ready else str(db_path),
    )
    report.add(
        "Publish trace table exists",
        any(c.name == "table_live_publish_trace" and c.passed for c in db_report.checks),
        "",
    )
    report.add(
        "Rollback repository healthy",
        any(c.name == "table_live_channel_publish_log" and c.passed for c in db_report.checks),
        "audit log table",
    )

    from bot.live_ops.controlled_factory import build_controlled_live_stack

    try:
        coord = build_controlled_live_stack(db_path)
        startup = await coord.startup()
        report.add(
            "Startup validation passed",
            bool(startup.get("passed")),
            str(startup),
        )
        results["startup"] = startup
    except Exception as exc:
        report.add("Startup validation passed", False, str(exc)[:120])

    for line in await simulate_operational_commands(db_path):
        report.lines.append(line)

    if args.health_url:
        try:
            with urllib.request.urlopen(
                f"{args.health_url.rstrip('/')}/pilot_readiness",
                timeout=5,
            ) as resp:
                body = json.loads(resp.read().decode())
                results["http"] = body
                report.add("HTTP pilot_readiness", bool(body.get("ready")), "")
        except Exception as exc:
            report.add("HTTP pilot_readiness", False, str(exc)[:80])

    print(report.render())

    if args.json_out:
        args.json_out.write_text(
            json.dumps(
                {
                    "ready": report.passed,
                    "lines": [
                        {"label": ln.label, "ok": ln.ok, "reason": ln.reason}
                        for ln in report.lines
                    ],
                    **results,
                },
                indent=2,
            ),
        )

    return 0 if report.passed or not args.strict else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled public pilot preflight")
    parser.add_argument("--env-file", type=Path, default=Path(".env.production"))
    parser.add_argument("--db", type=Path, default=None)
    parser.add_argument("--health-url", type=str, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--send-test-message",
        action="store_true",
        help="Send test to shadow + ops only (never public)",
    )
    parser.add_argument("--strict", action="store_true", default=True)
    parser.add_argument("--no-strict", action="store_false", dest="strict")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
