#!/usr/bin/env python3
"""Replace published channel photo with source media from collector cache."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _db_path() -> Path:
    candidate = Path(os.getenv("DATABASE_PATH", "var/newsroom.db"))
    if candidate.is_file():
        return candidate
    fallback = Path("/data/newsroom.db")
    return fallback if fallback.is_file() else candidate


async def _run(draft_id: int, *, message_id: int | None, media_path: str | None) -> int:
    from aiogram.types import FSInputFile, InputMediaPhoto
    from app.config import load_settings
    from app.telegram_bot import create_newsroom_bot
    from publisher.publish_formatting import build_channel_message_html
    from publisher.routing import route_draft_to_channel
    from utils.telegram_chunks import split_telegram_text

    c = sqlite3.connect(str(_db_path()))
    row = c.execute(
        "SELECT content, sources, draft_extras FROM drafts WHERE id=?",
        (draft_id,),
    ).fetchone()
    if not row:
        print({"error": "draft_not_found", "draft_id": draft_id})
        return 1
    content, sources, extras_json = row
    sources_list = json.loads(sources or "[]")
    src_msg = int(sources_list[0]["message_id"]) if sources_list else 0

    resolved_media = media_path
    if not resolved_media:
        cache_root = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime")) / "media_cache"
        if not cache_root.is_dir():
            cache_root = Path("/data/runtime/media_cache")
        matches = sorted(cache_root.glob(f"*_{src_msg}.jpg"))
        if not matches:
            matches = sorted(cache_root.glob(f"*_{src_msg}.mp4"))
        if not matches:
            print({"error": "media_not_found", "message_id": src_msg})
            return 1
        resolved_media = str(matches[0])

    if not Path(resolved_media).is_file():
        print({"error": "media_missing", "path": resolved_media})
        return 1

    chat_id_val = None
    stem = Path(resolved_media).stem
    if "_" in stem:
        try:
            chat_id_val = int(stem.rsplit("_", 1)[0])
        except ValueError:
            chat_id_val = None

    media = {
        "media_type": "photo" if resolved_media.endswith(".jpg") else "video",
        "local_path": resolved_media,
        "media_path": resolved_media,
        "media_status": "source_reused",
        "media_type_meta": "photo" if resolved_media.endswith(".jpg") else "video",
        "media_source_url": None,
        "media_generation_reason": "telethon_source",
        "media_fallback_used": False,
        "message_id": src_msg,
        "chat_id": chat_id_val,
    }
    extras = json.loads(extras_json or "{}")
    extras["media"] = media
    c.execute(
        "UPDATE drafts SET draft_extras=? WHERE id=?",
        (json.dumps(extras, ensure_ascii=False), draft_id),
    )
    if sources_list:
        ch = str(sources_list[0].get("channel") or "")
        c.execute(
            "UPDATE raw_posts SET extras=? WHERE channel_name=? AND message_id=?",
            (json.dumps({"media": media}, ensure_ascii=False), ch, src_msg),
        )
    c.commit()

    tg_msg = message_id
    if tg_msg is None:
        pp = c.execute(
            "SELECT telegram_post_id FROM published_posts WHERE draft_id=?",
            (draft_id,),
        ).fetchone()
        tg_msg = int(pp[0]) if pp else None
    c.close()
    if tg_msg is None:
        print({"error": "telegram_message_id_missing"})
        return 1

    settings = load_settings()
    bot = create_newsroom_bot(settings)
    try:
        chat_id = route_draft_to_channel(settings, sources=sources_list)
        html = build_channel_message_html(
            content,
            sources,
            draft_id=draft_id,
            include_sources=False,
            include_draft_id_footer=False,
        )
        chunks = split_telegram_text(html, respect_html=True)
        caption = chunks[0] if chunks and len(chunks[0]) <= 1024 else None
        media_input = InputMediaPhoto(
            media=FSInputFile(resolved_media),
            caption=caption,
            parse_mode="HTML",
        )
        await bot.edit_message_media(chat_id=chat_id, message_id=tg_msg, media=media_input)
        print(
            {
                "ok": True,
                "draft_id": draft_id,
                "chat_id": chat_id,
                "message_id": tg_msg,
                "media": resolved_media,
            }
        )
        return 0
    finally:
        await bot.session.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Fix published post media from collector cache")
    p.add_argument("draft_id", type=int)
    p.add_argument("--message-id", type=int, default=None)
    p.add_argument("--media-path", default=None)
    args = p.parse_args()
    return asyncio.run(_run(args.draft_id, message_id=args.message_id, media_path=args.media_path))


if __name__ == "__main__":
    raise SystemExit(main())
