"""Breaking lane — T0 sources, <5 min latency, bypass standard cadence."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.sources.registry import breaking_source_handles, load_active_source_handles
from collector.telethon_client import build_telethon_client
from collector.telethon_connect import connect_telethon_resilient
from db.models import RawPost
from db.session import session_scope
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_BREAKING_KEYWORDS = (
    "breaking",
    "urgent",
    "срочно",
    "экстрен",
    "взрыв",
    "attack",
    "war",
    "rate cut",
    "rate hike",
    "fed",
    "ecb",
    "sanctions",
    "default",
    "bankruptcy",
    "crash",
    "halt",
    "emergency",
)


def _breaking_enabled() -> bool:
    return os.getenv("BREAKING_LANE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def _cooldown_sec() -> int:
    try:
        return max(120, int(os.getenv("BREAKING_COOLDOWN_SEC", "600")))
    except ValueError:
        return 600


def _last_breaking_path(runtime_dir: str) -> str:
    from pathlib import Path

    return str(Path(runtime_dir) / "breaking_lane_state.json")


def _load_state(runtime_dir: str) -> dict[str, Any]:
    path = _last_breaking_path(runtime_dir)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"last_publish_ts": 0.0, "recent_hashes": []}


def _save_state(runtime_dir: str, state: dict[str, Any]) -> None:
    from pathlib import Path

    path = Path(_last_breaking_path(runtime_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f)


def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().lower()[:500].encode()).hexdigest()[:16]


def _is_breaking_signal(text: str) -> bool:
    low = (text or "").lower()
    if any(k in low for k in _BREAKING_KEYWORDS):
        return True
    if "!" in text and len(text) < 400:
        return True
    return False


def _lightweight_summarize(text: str, *, max_chars: int = 900) -> str:
    """Rule-based fast path — no LLM round-trip."""
    from app.reliability.summarize_fallback import rule_based_summary

    try:
        out = rule_based_summary(text, max_chars=max_chars)
        if out and len(out.strip()) >= 80:
            return out.strip()
    except Exception:
        pass
    t = " ".join((text or "").split())
    if len(t) > max_chars:
        cut = t[: max_chars - 3]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        t = cut + "…"
    return t


async def _fetch_recent_t0_posts(client: Any, handles: list[str], *, limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for handle in handles:
        try:
            entity = await client.get_entity(handle)
            async for msg in client.iter_messages(entity, limit=limit):
                text = getattr(msg, "message", None) or ""
                if not text or len(text.strip()) < 40:
                    continue
                out.append(
                    {
                        "channel": handle,
                        "message_id": int(msg.id),
                        "text": text.strip(),
                        "date": getattr(msg, "date", None),
                    }
                )
        except Exception as exc:
            log_event(logger, "breaking.collect_failed", channel=handle, error=repr(exc)[:120])
    return out


async def run_breaking_tick(ctx: Any) -> dict[str, Any]:
    """
    Scheduler job: poll T0 → lightweight gate → emergency publish.
    """
    settings = ctx.settings
    runtime_dir = settings.runtime_state_dir
    result: dict[str, Any] = {"published": False, "reason": "disabled"}
    if not _breaking_enabled():
        return result

    state = _load_state(runtime_dir)
    now = time.time()
    if now - float(state.get("last_publish_ts") or 0) < _cooldown_sec():
        result["reason"] = "cooldown"
        return result

    handles = breaking_source_handles(settings)
    if not handles:
        result["reason"] = "no_t0_sources"
        return result

    client = build_telethon_client(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telethon_session_string,
        session_path=settings.telethon_session_path,
    )
    if not await connect_telethon_resilient(client, label="breaking_collect"):
        result["reason"] = "telethon_connect_failed"
        return result

    posts = await _fetch_recent_t0_posts(client, handles, limit=int(os.getenv("BREAKING_FETCH_LIMIT", "5")))
    recent_hashes = set(state.get("recent_hashes") or [])
    candidate: dict[str, Any] | None = None
    for p in sorted(posts, key=lambda x: x.get("date") or datetime.min.replace(tzinfo=UTC), reverse=True):
        text = str(p.get("text") or "")
        if not _is_breaking_signal(text):
            continue
        h = _content_hash(text)
        if h in recent_hashes:
            continue
        async with session_scope() as session:
            q = select(RawPost.id).where(
                RawPost.channel_name == str(p.get("channel") or ""),
                RawPost.message_id == int(p.get("message_id") or 0),
            )
            if (await session.execute(q)).scalar_one_or_none() is not None:
                continue
        candidate = p
        candidate["_hash"] = h
        break

    if not candidate:
        result["reason"] = "no_breaking_candidate"
        return result

    summary = _lightweight_summarize(str(candidate.get("text") or ""))
    from app.ops.floor_eligibility import evaluate_floor_eligibility

    sources = json.dumps([{"channel": candidate["channel"], "message_id": candidate["message_id"]}])
    elig = evaluate_floor_eligibility(summary, sources_json=sources)
    if not elig.eligible:
        from app.editorial.content_quality import has_hidden_advertising, is_truncated_mid_thought

        if has_hidden_advertising(summary) or is_truncated_mid_thought(summary):
            result["reason"] = f"gate_blocked:{elig.reason}"
            return result

    article_id = f"brk:{candidate['_hash']}"
    try:
        from app.worker.fast_publish import publish_breaking_item

        msg_id = await publish_breaking_item(
            ctx.bot,
            settings,
            content=summary,
            sources=json.loads(sources),
            article_id=article_id,
        )
    except Exception as exc:
        log_event(logger, "breaking.publish_failed", error=repr(exc)[:200])
        result["reason"] = f"publish_failed:{repr(exc)[:80]}"
        return result

    recent_hashes.add(candidate["_hash"])
    state["recent_hashes"] = list(recent_hashes)[-50:]
    state["last_publish_ts"] = now
    _save_state(runtime_dir, state)

    try:
        from app.analytics.telegram_stats import enqueue_post_for_tracking

        await enqueue_post_for_tracking(
            draft_id=None,
            telegram_post_id=int(msg_id),
            channel_id=int(settings.channel_id),
            primary_source=str(candidate.get("channel") or ""),
            topic_bucket="breaking",
        )
    except Exception:
        pass

    result["published"] = True
    result["message_id"] = msg_id
    result["reason"] = "ok"
    log_event(logger, "breaking.tick_complete", message_id=msg_id, channel=candidate.get("channel"))
    return result
