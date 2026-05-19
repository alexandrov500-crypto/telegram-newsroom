#!/usr/bin/env python3
"""List Telegram chats/channels the bot can see (from updates + configured env IDs)."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _chat_key(chat: Any) -> int:
    return int(chat.id)


async def webhook_pending_count(bot) -> int:
    try:
        wh = await bot.get_webhook_info()
        return int(wh.pending_update_count or 0)
    except Exception:
        return 0


async def collect_chat_ids_from_updates(bot) -> dict[int, str]:
    """Return chat_id -> discovery source from pending updates."""
    found: dict[int, str] = {}
    offset: int | None = None
    for _ in range(10):
        kwargs: dict[str, Any] = {
            "limit": 100,
            "timeout": 1,
            "allowed_updates": [
                "message",
                "channel_post",
                "my_chat_member",
                "chat_member",
            ],
        }
        if offset is not None:
            kwargs["offset"] = offset
        updates = await bot.get_updates(**kwargs)
        if not updates:
            break
        for upd in updates:
            chat = None
            if upd.message and upd.message.chat:
                chat = upd.message.chat
            elif upd.channel_post and upd.channel_post.chat:
                chat = upd.channel_post.chat
            elif upd.my_chat_member and upd.my_chat_member.chat:
                chat = upd.my_chat_member.chat
            elif upd.chat_member and upd.chat_member.chat:
                chat = upd.chat_member.chat
            if chat is None:
                continue
            cid = _chat_key(chat)
            if cid not in found:
                found[cid] = "getUpdates"
            offset = upd.update_id + 1
        if len(updates) < 100:
            break
    return found


def _format_permissions(perms) -> str:
    if perms is None:
        return "no access / not a member"
    if not perms.is_admin:
        return "member (not admin)"
    bits = []
    if perms.can_post_messages:
        bits.append("post")
    if perms.can_edit_messages:
        bits.append("edit")
    if perms.can_delete_messages:
        bits.append("delete")
    if perms.can_invite_users:
        bits.append("invite")
    if perms.can_manage_chat:
        bits.append("manage")
    return "admin: " + (", ".join(bits) if bits else "no post/edit/delete flags")


async def describe_chat(bot, chat_id: int, *, source: str) -> dict[str, Any]:
    from bot.live_ops.telegram_pilot import fetch_channel_permissions

    title = str(chat_id)
    chat_type = "unknown"
    username = ""
    try:
        chat = await bot.get_chat(chat_id)
        title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or title
        chat_type = getattr(chat, "type", "unknown")
        if hasattr(chat_type, "value"):
            chat_type = chat_type.value
        username = getattr(chat, "username", None) or ""
    except Exception as exc:
        return {
            "id": chat_id,
            "title": title,
            "type": chat_type,
            "username": username,
            "permissions": f"getChat failed: {exc}",
            "source": source,
            "reachable": False,
        }

    perms = await fetch_channel_permissions(bot, chat_id)
    return {
        "id": chat_id,
        "title": title,
        "type": str(chat_type),
        "username": f"@{username}" if username else "",
        "permissions": _format_permissions(perms),
        "source": source,
        "reachable": True,
    }


def _env_channel_ids() -> list[tuple[str, int | None]]:
    out: list[tuple[str, int | None]] = []
    for label, key in (
        ("LIVE_PUBLIC_CHANNEL_ID", "LIVE_PUBLIC_CHANNEL_ID"),
        ("LIVE_OPS_CHANNEL_ID", "LIVE_OPS_CHANNEL_ID"),
        ("LIVE_SHADOW_CHANNEL_ID", "LIVE_SHADOW_CHANNEL_ID"),
        ("TELEGRAM_CHANNEL_ID", "TELEGRAM_CHANNEL_ID"),
        ("TELEGRAM_OPERATOR_CHAT_ID", "TELEGRAM_OPERATOR_CHAT_ID"),
        ("TELEGRAM_DIGEST_CHANNEL_ID", "TELEGRAM_DIGEST_CHANNEL_ID"),
    ):
        raw = os.getenv(key, "").strip()
        if not raw:
            continue
        try:
            cid = int(raw)
        except ValueError:
            continue
        if not any(c == cid for _, c in out):
            out.append((label, cid))
    return out


def print_chat_block(info: dict[str, Any], *, role_hint: str = "") -> None:
    role = f" ({role_hint})" if role_hint else ""
    print(f"{info['title']}{role}")
    print(f"  ID:          {info['id']}")
    print(f"  Type:        {info['type']}")
    if info.get("username"):
        print(f"  Username:    {info['username']}")
    print(f"  Permissions: {info['permissions']}")
    print(f"  Source:      {info['source']}")
    print()


async def main_async(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    token = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Set BOT_TOKEN or TELEGRAM_BOT_TOKEN in .env", file=sys.stderr)
        return 1

    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    from bot.live_ops.telegram_pilot import authenticate_bot_instance

    bot = Bot(token=token, default=DefaultBotProperties())
    try:
        me = await authenticate_bot_instance(bot)
        print("=" * 52)
        print(f"Bot: @{me.username} (id={me.id})")
        print("=" * 52)
        print()

        ids_to_probe: dict[int, str] = {}

        if args.chat_id:
            ids_to_probe[int(args.chat_id)] = "CLI --chat-id"
        else:
            for label, cid in _env_channel_ids():
                if cid is not None:
                    ids_to_probe[cid] = f"env {label}"
            from_updates = await collect_chat_ids_from_updates(bot)
            for cid, src in from_updates.items():
                ids_to_probe.setdefault(cid, src)

        pending = await webhook_pending_count(bot)
        if pending:
            print(f"Telegram queue: {pending} pending update(s) (will be read now)\n")
        elif not ids_to_probe:
            print("Telegram queue: 0 pending updates\n")

        if not ids_to_probe:
            print("No chats found.")
            print()
            print("Common causes:")
            print("  • Operator bot is running (docker/main.py) — it consumes updates.")
            print("    Stop it, post in channel again, re-run this script.")
            print("  • No activity yet — send /start to the bot, add bot as channel admin, post once.")
            print()
            print("Workaround — probe channel ID directly:")
            print("  python3 scripts/list_telegram_channels.py --chat-id -1003934479919")
            print()
            print("Or forward a channel post to @getidsbot to see the ID.")
            return 0

        env_public = os.getenv("LIVE_PUBLIC_CHANNEL_ID") or os.getenv("TELEGRAM_CHANNEL_ID")
        env_ops = os.getenv("LIVE_OPS_CHANNEL_ID") or os.getenv("TELEGRAM_OPERATOR_CHAT_ID")
        env_shadow = os.getenv("LIVE_SHADOW_CHANNEL_ID") or os.getenv("TELEGRAM_DIGEST_CHANNEL_ID")

        print(f"Found {len(ids_to_probe)} chat(s):\n")

        for cid in sorted(ids_to_probe.keys()):
            source = ids_to_probe[cid]
            info = await describe_chat(bot, cid, source=source)
            hint = ""
            if env_public and str(cid) == str(env_public).strip():
                hint = "configured public / TELEGRAM_CHANNEL"
            elif env_ops and str(cid) == str(env_ops).strip():
                hint = "configured ops / OPERATOR_CHAT"
            elif env_shadow and str(cid) == str(env_shadow).strip():
                hint = "configured shadow / digest"
            print_chat_block(info, role_hint=hint)

        print("-" * 52)
        print("Copy to .env (example):")
        channels = sorted(ids_to_probe.keys())
        for i, cid in enumerate(channels):
            t = (await describe_chat(bot, cid, source="")).get("type", "")
            if t == "channel" and not env_public:
                print(f"LIVE_PUBLIC_CHANNEL_ID={cid}")
                print(f"TELEGRAM_CHANNEL_ID={cid}")
                break
        print("-" * 52)

    finally:
        await bot.session.close()

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List Telegram chats/channels visible to the bot",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(".env"),
        help="Env file with BOT_TOKEN (default: .env)",
    )
    parser.add_argument(
        "--chat-id",
        type=int,
        default=None,
        help="Probe a specific chat/channel ID (e.g. -1001234567890)",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
