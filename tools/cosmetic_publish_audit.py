#!/usr/bin/env python3
"""Audit recent publishes for cosmetic media defects (fallback when source exists)."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@dataclass(frozen=True)
class CosmeticIssue:
    draft_id: int
    status: str
    issue: str
    source_message_id: int | None
    cache_path: str | None
    telegram_post_id: int | None
    fixable: bool


def _db_path() -> Path:
    candidate = Path(os.getenv("DATABASE_PATH", "var/newsroom.db"))
    if candidate.is_file():
        return candidate
    fallback = Path("/data/newsroom.db")
    return fallback if fallback.is_file() else candidate


def _cache_root() -> Path:
    root = Path(os.getenv("RUNTIME_STATE_DIR", "var/runtime")) / "media_cache"
    if root.is_dir():
        return root
    fallback = Path("/data/runtime/media_cache")
    return fallback if fallback.is_dir() else root


def _source_message_id(sources_json: str | None) -> int | None:
    try:
        sources = json.loads(sources_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return None
    if not sources or not isinstance(sources[0], dict):
        return None
    try:
        return int(sources[0]["message_id"])
    except (KeyError, TypeError, ValueError):
        return None


def _find_cache(cache_root: Path, message_id: int) -> str | None:
    for ext in (".jpg", ".mp4"):
        matches = sorted(cache_root.glob(f"*_{message_id}{ext}"))
        for path in matches:
            if path.is_file() and path.stat().st_size >= 512:
                return str(path)
    return None


def audit_recent(*, limit: int = 20) -> list[CosmeticIssue]:
    cache_root = _cache_root()
    conn = sqlite3.connect(str(_db_path()))
    try:
        rows = conn.execute(
            """
            SELECT d.id, d.status, d.sources, d.draft_extras, pp.telegram_post_id
            FROM drafts d
            LEFT JOIN published_posts pp ON pp.draft_id = d.id
            WHERE d.status IN ('published', 'pending', 'scheduled')
            ORDER BY d.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    finally:
        conn.close()

    issues: list[CosmeticIssue] = []
    for draft_id, status, sources, extras_json, tg_post in rows:
        try:
            extras = json.loads(extras_json or "{}")
        except (json.JSONDecodeError, TypeError):
            extras = {}
        media = extras.get("media") if isinstance(extras, dict) else None
        if not isinstance(media, dict):
            continue
        if not media.get("media_fallback_used"):
            continue
        src_msg = _source_message_id(sources)
        cache_path = _find_cache(cache_root, src_msg) if src_msg is not None else None
        if cache_path:
            issues.append(
                CosmeticIssue(
                    draft_id=int(draft_id),
                    status=str(status),
                    issue="fallback_with_source_cache",
                    source_message_id=src_msg,
                    cache_path=cache_path,
                    telegram_post_id=int(tg_post) if tg_post is not None else None,
                    fixable=True,
                )
            )
        elif src_msg is not None:
            issues.append(
                CosmeticIssue(
                    draft_id=int(draft_id),
                    status=str(status),
                    issue="fallback_text_only_source",
                    source_message_id=src_msg,
                    cache_path=None,
                    telegram_post_id=int(tg_post) if tg_post is not None else None,
                    fixable=False,
                )
            )
    return issues


def _patch_pending_draft_media(
    draft_id: int,
    cache_path: str,
    source_message_id: int | None,
) -> None:
    chat_id_val = None
    stem = Path(cache_path).stem
    if "_" in stem:
        try:
            chat_id_val = int(stem.rsplit("_", 1)[0])
        except ValueError:
            chat_id_val = None
    media = {
        "media_type": "photo" if cache_path.endswith(".jpg") else "video",
        "local_path": cache_path,
        "media_path": cache_path,
        "media_status": "source_reused",
        "media_type_meta": "photo" if cache_path.endswith(".jpg") else "video",
        "media_source_url": None,
        "media_generation_reason": "telethon_source",
        "media_fallback_used": False,
        "message_id": source_message_id,
        "chat_id": chat_id_val,
    }
    conn = sqlite3.connect(str(_db_path()))
    try:
        row = conn.execute("SELECT draft_extras, sources FROM drafts WHERE id=?", (draft_id,)).fetchone()
        if not row:
            return
        extras = json.loads(row[0] or "{}")
        if not isinstance(extras, dict):
            extras = {}
        extras["media"] = media
        conn.execute(
            "UPDATE drafts SET draft_extras=? WHERE id=?",
            (json.dumps(extras, ensure_ascii=False), draft_id),
        )
        sources_list = json.loads(row[1] or "[]")
        if sources_list and isinstance(sources_list[0], dict):
            ch = str(sources_list[0].get("channel") or "")
            msg = int(sources_list[0].get("message_id") or 0)
            if ch and msg:
                conn.execute(
                    "UPDATE raw_posts SET extras=? WHERE channel_name=? AND message_id=?",
                    (json.dumps({"media": media}, ensure_ascii=False), ch, msg),
                )
        conn.commit()
        print({"fixed_pending": draft_id, "media": cache_path})
    finally:
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser(description="Audit cosmetic media defects in recent drafts")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix published drafts where source cache exists",
    )
    args = p.parse_args()
    issues = audit_recent(limit=max(1, args.limit))
    fixable = [i for i in issues if i.fixable]
    if args.fix and fixable:
        import asyncio
        import subprocess

        for item in fixable:
            if item.status == "published" and item.telegram_post_id:
                subprocess.run(
                    [sys.executable, str(REPO / "tools" / "fix_published_media.py"), str(item.draft_id)],
                    check=False,
                )
            elif item.status in ("pending", "scheduled") and item.cache_path:
                _patch_pending_draft_media(item.draft_id, item.cache_path, item.source_message_id)
    payload = {
        "issue_count": len(issues),
        "fixable_count": len(fixable),
        "issues": [asdict(i) for i in issues],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"cosmetic_audit issues={payload['issue_count']} fixable={payload['fixable_count']}"
        )
        for item in issues:
            line = (
                f"draft={item.draft_id} status={item.status} "
                f"issue={item.issue} src_msg={item.source_message_id}"
            )
            if item.cache_path:
                line += f" cache={item.cache_path}"
            if item.telegram_post_id:
                line += f" tg={item.telegram_post_id}"
            print(line)
    return 1 if payload["fixable_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
