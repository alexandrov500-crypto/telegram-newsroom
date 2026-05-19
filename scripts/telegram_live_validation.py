#!/usr/bin/env python3
"""Live Telegram channel validation before public deployment."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
    remediation: str = ""


@dataclass
class ValidationReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add(self, name: str, ok: bool, detail: str, remediation: str = "") -> None:
        self.checks.append(CheckResult(name, ok, detail, remediation))

    def print_report(self) -> None:
        print("Telegram live validation report")
        print("=" * 40)
        for c in self.checks:
            mark = "PASS" if c.passed else "FAIL"
            print(f"[{mark}] {c.name}: {c.detail}")
            if not c.passed and c.remediation:
                print(f"       → {c.remediation}")
        print("=" * 40)
        print(f"Overall: {'READY' if self.passed else 'NOT READY'}")


async def run_validation(*, token: str, channel_id: int, operator_chat_id: int | None) -> ValidationReport:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ChatMemberStatus, ParseMode
    from aiogram.exceptions import TelegramRetryAfter
    from aiogram.types import ChatMemberAdministrator

    from bot.go_live.telegram_activation import ProductionTelegramActivation

    report = ValidationReport()
    bot = Bot(token=token, default=DefaultBotProperties())

    try:
        me = await bot.get_me()
        report.add("bot_getMe", True, f"@{me.username}")

        activation = ProductionTelegramActivation(
            bot,
            channel_id=channel_id,
            operator_chat_id=operator_chat_id,
            admin_user_ids=frozenset(),
            strict_permissions=True,
        )
        act = await activation.run(shadow_publish_only=True)
        if act.channel:
            c = act.channel
            report.add(
                "admin_post",
                c.can_post_messages,
                "can_post_messages",
                "Add bot as admin with Post Messages",
            )
            report.add(
                "admin_edit",
                c.can_edit_messages,
                "can_edit_messages",
                "Enable Edit messages for bot",
            )
            report.add(
                "admin_delete",
                c.can_delete_messages,
                "can_delete_messages",
                "Enable Delete messages for bot",
            )
            report.add(
                "admin_invite",
                c.can_invite_users,
                "can_invite_users",
                "Enable Invite users (optional but required by policy)",
            )
            report.add(
                "admin_manage",
                c.can_manage_chat,
                "can_manage_chat",
                "Enable Manage chat for bot",
            )
            if c.linked_discussion_id:
                report.add(
                    "discussion_group",
                    True,
                    f"linked {c.linked_discussion_id}",
                )
            else:
                report.add(
                    "discussion_group",
                    True,
                    "none linked (optional)",
                )
        else:
            report.add("channel_access", False, "channel unreachable", "Add bot to channel")

        report.add(
            "publish_probe",
            act.publish_probe_ok,
            "send/delete test",
            "Verify bot can post in channel",
        )

        # HTML rendering probe
        probe_id: int | None = None
        try:
            msg = await bot.send_message(
                channel_id,
                "<b>Live validation</b> <i>HTML</i> ✓",
                parse_mode=ParseMode.HTML,
                disable_notification=True,
            )
            probe_id = msg.message_id
            report.add("html_render", True, "HTML parse OK")
        except Exception as exc:
            report.add("html_render", False, str(exc)[:120], "Fix HTML in templates")

        if probe_id:
            try:
                await bot.edit_message_text(
                    "<b>Live validation</b> edited",
                    chat_id=channel_id,
                    message_id=probe_id,
                    parse_mode=ParseMode.HTML,
                )
                report.add("edit_test", True, "edit OK")
            except Exception as exc:
                report.add("edit_test", False, str(exc)[:80], "Grant edit permission")

            try:
                await bot.delete_message(channel_id, probe_id)
                report.add("delete_test", True, "delete OK")
            except Exception as exc:
                report.add("delete_test", False, str(exc)[:80], "Grant delete permission")

        if operator_chat_id:
            try:
                await bot.send_message(
                    operator_chat_id,
                    "[validation] operator command path OK",
                    disable_notification=True,
                )
                report.add(
                    "operator_chat",
                    True,
                    "operator reachable",
                )
            except Exception as exc:
                report.add(
                    "operator_chat",
                    False,
                    str(exc)[:80],
                    "Start chat with bot from operator account",
                )

        # FloodWait safety (soft)
        try:
            await bot.get_chat(channel_id)
            report.add("floodwait", True, "no FloodWait on getChat")
        except TelegramRetryAfter as exc:
            report.add(
                "floodwait",
                False,
                f"retry_after={exc.retry_after}",
                "Wait and reduce probe frequency",
            )

    finally:
        await bot.session.close()

    return report


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env.production"))
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()
    load_env_file(args.env_file)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    ch = os.environ.get("TELEGRAM_CHANNEL_ID") or os.environ.get("TELEGRAM_DIGEST_CHANNEL_ID")
    op = os.environ.get("TELEGRAM_OPERATOR_CHAT_ID")

    if not token or not ch:
        print("TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID required", file=sys.stderr)
        return 1

    report = asyncio.run(
        run_validation(
            token=token,
            channel_id=int(ch),
            operator_chat_id=int(op) if op else None,
        ),
    )
    report.print_report()
    if args.json_out:
        args.json_out.write_text(
            json.dumps(
                {
                    "passed": report.passed,
                    "checks": [
                        {
                            "name": c.name,
                            "passed": c.passed,
                            "detail": c.detail,
                            "remediation": c.remediation,
                        }
                        for c in report.checks
                    ],
                },
                indent=2,
            ),
        )
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
