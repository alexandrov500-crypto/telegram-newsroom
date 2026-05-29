from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.enums import ChatType, ParseMode
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.config import Settings
from bot.admin_access import can_handle_admin_callback, can_handle_admin_message
from bot.callback_answer import callback_ack
from bot.callback_middleware import SafeCallbackMiddleware
from bot.handler_error_middleware import SafeHandlerMiddleware
from bot.keyboards import draft_actions_keyboard, queue_pagination_keyboard
from db.models import DraftStatus
from db.repository import (
    draft_duplicate_intel,
    get_draft_by_id,
    list_pending_drafts_for_queue,
    list_scheduled_drafts,
    merge_draft_extras,
    reject_draft,
    schedule_draft_publish,
    search_drafts_operational,
    set_draft_admin_message,
    update_draft_content,
    update_draft_summary,
    update_draft_title,
    utcnow,
)
from db.session import session_scope
from publisher.formatting import render_draft_preview
from publisher.public_renderer import render_internal_review_html
from publisher.telegram_transport import send_channel_photo, send_channel_video
from publisher.publish_service import (
    AdminPublishDraftResult as _AdminPublishDraftResult,
    PublishFlowOutcome as _PublishFlowOutcome,
    execute_admin_publication_flow as _admin_publish_draft_flow,
)
from ai.editorial_enhancer import apply_optional_title_enhancement
from ai.editorial_titles import generate_title_suggestions
from ai.editorial_rewrite import rewrite_draft
from editorial.diffing import format_edit_history, headline_and_lead_diff
from editorial.explanations import explain_from_draft_extras, explain_suppression
from utils.diagnostics import (
    asyncio_task_count,
    db_file_size_bytes,
    process_uptime_sec,
    quick_db_ping_ok,
    rss_bytes_best_effort,
)
from utils.metrics import avg_pipeline_duration_sec, snapshot
from utils.structured_log import log_event
from utils.schedule_parse import parse_draft_schedule_at
from utils.telegram_chunks import SAFE_CHUNK, TELEGRAM_MAX_MESSAGE_LENGTH, split_telegram_text

logger = logging.getLogger(__name__)

router = Router(name="admin")
_fallback_router = Router(name="admin_fallback")


_MAX_CALLBACK_DRAFT_ID = 500_000_000


def _parse_slash_command_int(command: str, text: str | None) -> int | None:
    if not text:
        return None
    m = re.match(rf"^/{command}(?:@\S+)?\s+(\d+)\s*$", text.strip())
    if not m:
        return None
    n = int(m.group(1))
    if n <= 0 or n > _MAX_CALLBACK_DRAFT_ID:
        return None
    return n


def _parse_callback_draft_id(callback_data: str | None) -> int | None:
    try:
        rest = (callback_data or "").split(":", 1)[1]
        n = int(rest)
    except (ValueError, IndexError):
        return None
    if n <= 0 or n > _MAX_CALLBACK_DRAFT_ID:
        return None
    return n


_QUEUE_PAGE_SIZE = 7


def _parse_queue_command(text: str | None) -> tuple[int, str]:
    raw = (text or "").strip()
    m = re.match(r"^/queue(?:@\S+)?(?:\s+(.*))?$", raw)
    rest = (m.group(1) or "").strip() if m else ""
    if not rest:
        return 0, "fifo"
    parts = rest.split()
    mode = "fifo"
    i0 = 0
    if parts[0].lower() in ("priority", "breaking", "fifo"):
        mode = parts[0].lower()
        i0 = 1
    page_one = 1
    if i0 < len(parts) and parts[i0].isdigit():
        page_one = int(parts[i0])
    return max(0, page_one - 1), mode


def _extras_json_for_preview(draft: Any, settings: Settings) -> str:
    try:
        ex = json.loads(draft.draft_extras or "{}")
    except (json.JSONDecodeError, TypeError):
        ex = {}
    if not isinstance(ex, dict):
        ex = {}
    try:
        from utils.source_reputation import export_channel_scores_for_priority

        rep_map = export_channel_scores_for_priority(settings.runtime_state_dir)
        channels: list[str] = []
        try:
            data = json.loads(draft.sources or "[]")
        except (json.JSONDecodeError, TypeError):
            data = []
        if isinstance(data, list):
            for it in data:
                if isinstance(it, dict) and it.get("channel"):
                    channels.append(str(it.get("channel")).strip())
        sub: dict[str, Any] = {}
        for ch in channels:
            if not ch:
                continue
            row = rep_map.get(ch.lower()) or {}
            if isinstance(row, dict) and row:
                sub[ch] = {
                    k: row[k]
                    for k in ("score", "approval_rate", "publishes", "rejects", "duplicate_signals")
                    if k in row
                }
        if sub:
            ex["source_reputation"] = sub
    except Exception:
        pass
    return json.dumps(ex, ensure_ascii=False, sort_keys=True)


def _queue_line_badges(d: Any, *, now) -> str:
    badges: list[str] = []
    try:
        ex = json.loads(d.draft_extras or "{}")
    except (json.JSONDecodeError, TypeError):
        ex = {}
    if not isinstance(ex, dict):
        ex = {}
    pri = ex.get("priority") if isinstance(ex.get("priority"), dict) else {}
    brk = ex.get("breaking") if isinstance(ex.get("breaking"), dict) else {}
    dup = ex.get("duplicate_intel") if isinstance(ex.get("duplicate_intel"), dict) else {}
    if str(pri.get("priority_level") or "").upper() == "HIGH":
        badges.append("HI")
    if brk.get("is_breaking"):
        badges.append("BRK")
    if str(dup.get("severity") or "").lower() == "high":
        badges.append("DUP")
    if d.created_at is not None:
        cdt = d.created_at if d.created_at.tzinfo else d.created_at.replace(tzinfo=timezone.utc)
        age_h = max(0.0, (now - cdt.astimezone(timezone.utc)).total_seconds() / 3600.0)
        if age_h >= 48.0:
            badges.append("STALE")
    return f"[{'/'.join(badges)}] " if badges else ""


def _queue_page_zero_based(text: str | None) -> int:
    page, _mode = _parse_queue_command(text)
    return page


def _parse_id_and_rest(command: str, text: str | None) -> tuple[int, str] | None:
    m = re.match(rf"^/{command}(?:@\S+)?\s+(\d+)\s+(.+)$", (text or "").strip(), re.DOTALL)
    if not m:
        return None
    rest = m.group(2).strip()
    if not rest:
        return None
    return int(m.group(1)), rest


def _parse_schedule_command(text: str | None) -> tuple[int, str] | None:
    m = re.match(r"^/schedule(?:@\S+)?\s+(\d+)\s+(.+)$", (text or "").strip(), re.DOTALL)
    if not m:
        return None
    rest = m.group(2).strip()
    if not rest:
        return None
    return int(m.group(1)), rest


def _parse_find_command(text: str | None) -> dict[str, str]:
    """Parse ``/find topic:foo entity:bar status:pending`` style tokens."""
    raw = (text or "").strip()
    m = re.match(r"^/find(?:@\S+)?\s*(.*)$", raw, re.DOTALL)
    rest = (m.group(1) or "").strip() if m else ""
    out: dict[str, str] = {}
    for tok in rest.split():
        if ":" not in tok:
            continue
        k, v = tok.split(":", 1)
        key = k.strip().lower()
        if key in ("topic", "entity", "fingerprint", "suppression", "status"):
            out[key] = v.strip()
    return out


async def _queue_page_content(settings: Settings, *, page: int, mode: str = "fifo") -> tuple[str, bool, bool]:
    """Returns (text, has_next, any_rows)."""
    mode_key = mode if mode in ("fifo", "priority", "breaking") else "fifo"
    offset = page * _QUEUE_PAGE_SIZE
    now = utcnow()
    async with session_scope() as session:
        rows = await list_pending_drafts_for_queue(
            session,
            limit=_QUEUE_PAGE_SIZE + 1,
            offset=offset,
            mode=mode_key,
        )
    has_next = len(rows) > _QUEUE_PAGE_SIZE
    rows = rows[:_QUEUE_PAGE_SIZE]
    if not rows:
        return ("Нет черновиков в очереди.", False, False)
    lines: list[str] = []
    for d in rows:
        head = (d.editor_title or "").strip() or (
            (d.content or "").splitlines()[0].strip() if (d.content or "").splitlines() else ""
        )
        if len(head) > 72:
            head = head[:69] + "…"
        sch = ""
        if d.scheduled_publish_at:
            sch = f" ⏱{d.scheduled_publish_at.isoformat()[:16]}"
        badges = _queue_line_badges(d, now=now)
        lines.append(f"{badges}#{d.id}\t{head}{sch}")
    mode_ru = {"fifo": "FIFO", "priority": "по приоритету", "breaking": "срочные первыми"}.get(
        mode_key, mode_key
    )
    body = f"Очередь черновиков (стр. {page + 1}, {mode_ru}):\n" + "\n".join(lines)
    if len(body) > 3500:
        body = body[:3490] + "\n…"
    return (body, has_next, True)


class SettingsMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["settings"] = self.settings
        return await handler(event, data)


def format_draft_message(*, draft_id: int, content: str, sources: str) -> str:
    from html import escape

    from app.publisher.draft_builder import finalize_draft_content

    safe_content = escape(finalize_draft_content(content, max_chars=3500))
    safe_sources = escape(sources)
    header = escape(f"Черновик #{draft_id}")
    return f"<b>{header}</b>\n\n{safe_content}\n\n<b>Источники (внутр.)</b>\n<pre>{safe_sources}</pre>"


async def _callback_user_feedback(callback: CallbackQuery, text: str) -> None:
    """After callback.answer(), send visible feedback in the chat."""
    if callback.message is None:
        return
    try:
        await callback.message.answer(text[:3500], disable_web_page_preview=True)
    except Exception as exc:
        log_event(logger, "bot.callback_feedback_failed", error=repr(exc))


async def _strip_markup_safe(message: Message | None) -> None:
    if message is None:
        return
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


def _message_has_media_caption(message: Message) -> bool:
    return bool(getattr(message, "photo", None) or getattr(message, "video", None))


async def _edit_admin_draft_footer(
    message: Message | None,
    *,
    draft_id: int,
    content: str,
    sources: str,
    footer_html: str,
) -> None:
    if message is None:
        return
    base = format_draft_message(draft_id=draft_id, content=content, sources=sources)
    full = f"{base}\n\n{footer_html}"
    if len(full) > TELEGRAM_MAX_MESSAGE_LENGTH:
        full = full[: TELEGRAM_MAX_MESSAGE_LENGTH - 20] + "\n…(truncated)"
    try:
        if _message_has_media_caption(message):
            await message.edit_caption(
                caption=full,
                reply_markup=None,
                parse_mode=ParseMode.HTML,
            )
        else:
            await message.edit_text(full, reply_markup=None, parse_mode=ParseMode.HTML)
    except Exception as exc:
        log_event(logger, "bot.edit_draft_message_failed", error=repr(exc))
        try:
            await message.answer(full, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            pass


def _admin_private_approval(callback: CallbackQuery, settings: Settings) -> bool:
    return can_handle_admin_callback(callback, settings)


def _admin_private_message(message: Message, settings: Settings) -> bool:
    return can_handle_admin_message(message, settings)


@router.message(Command("start"))
async def cmd_start(message: Message, settings: Settings) -> None:
    if not can_handle_admin_message(message, settings):
        await message.answer("Access denied.")
        return
    await message.answer(
        "Бот редакции Newsroom активен.\n\n"
        "Новые черновики приходят с кнопками:\n"
        "✅ Опубликовать · ⛔ Отклонить · 📅 Расписание · 👁 Превью\n"
        "💡 Объяснить · 📑 Сравнить · ✨ Заголовок\n\n"
        "Команды: /queue /draft &lt;id&gt; /schedule &lt;id&gt; ЧЧ:ММ /publish &lt;id&gt;",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("health"))
async def cmd_health(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    db_ok = await quick_db_ping_ok()
    lines = [
        f"db_ping={'ok' if db_ok else 'fail'}",
        f"uptime_sec={round(process_uptime_sec(), 1)}",
        f"asyncio_tasks={asyncio_task_count()}",
        f"rss_bytes={rss_bytes_best_effort()}",
        f"db_file_bytes={db_file_size_bytes(settings)}",
        f"dry_run={settings.dry_run}",
        f"soak_test={settings.soak_test}",
    ]
    try:
        from app.editorial.soft_launch import is_soft_launch_mode

        lines.append(f"soft_launch={is_soft_launch_mode()}")
    except Exception:
        pass
    port = int(getattr(settings, "health_http_port", 0) or 0)
    if port > 0:
        try:
            import urllib.request

            url = f"http://127.0.0.1:{port}/health"
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            lines.append(f"http_health={payload.get('status', '?')}")
            staging = payload.get("staging") or {}
            if staging.get("launch_ready") is not None:
                lines.append(f"launch_ready={staging.get('launch_ready')}")
        except Exception as exc:
            lines.append(f"http_health=unreachable ({exc.__class__.__name__})")
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@router.message(Command("metrics"))
async def cmd_metrics(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    snap = snapshot()
    avg = avg_pipeline_duration_sec()
    parts = [f"{k}={v}" for k, v in sorted(snap.items())]
    if avg is not None:
        parts.append(f"avg_pipeline_duration_sec={round(avg, 4)}")
    text = "\n".join(parts)
    if len(text) > 3500:
        text = text[:3490] + "\n…"
    await message.answer(text, disable_web_page_preview=True)


@router.message(Command("pipeline_status"))
async def cmd_pipeline_status(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    ctx = get_pipeline_context()
    if ctx is None:
        await message.answer("pipeline context unavailable")
        return
    body = "\n".join(
        [
            f"tick_in_progress={ctx.tick_in_progress}",
            f"last_wall_sec={round(ctx.last_scheduler_wall_sec, 4)}",
            f"timings_json={json.dumps(ctx.tick_timings, default=str)}",
        ]
    )
    if len(body) > 3500:
        body = body[:3490] + "\n…"
    await message.answer(body, disable_web_page_preview=True)


@router.message(Command("queue"))
async def cmd_queue(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    page, mode = _parse_queue_command(message.text)
    body, has_next, _any = await _queue_page_content(settings, page=page, mode=mode)
    kb = queue_pagination_keyboard(page=page, has_next=has_next, mode=mode)
    await message.answer(
        body,
        reply_markup=kb if kb.inline_keyboard else None,
        disable_web_page_preview=True,
    )


@router.message(Command("draft"))
async def cmd_draft(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    draft_id = _parse_slash_command_int("draft", message.text)
    if draft_id is None:
        await message.answer("Usage: /draft <id>")
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            await message.answer("Draft not found.")
            return
        intel = await draft_duplicate_intel(
            session,
            draft_id,
            similarity_threshold=settings.draft_similarity_threshold,
        )
    html = render_internal_review_html(
        draft_id,
        draft.content or "",
        draft.sources,
        editor_title=draft.editor_title,
        editor_summary=draft.editor_summary,
        draft_extras_json=_extras_json_for_preview(draft, settings),
        status=draft.status,
        created_at_iso=draft.created_at.isoformat() if draft.created_at else "",
        scheduled_at_iso=draft.scheduled_publish_at.isoformat() if draft.scheduled_publish_at else None,
        duplicate_intel=intel,
    )
    if len(html) > 3800:
        html = html[:3780] + "\n<i>…truncated</i>"
    await message.answer(html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@router.message(Command("preview_channel"))
async def cmd_preview_channel(message: Message, settings: Settings) -> None:
    """Channel publish preview — same HTML as ``build_channel_message_html``."""
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    draft_id = _parse_slash_command_int("preview_channel", message.text)
    if draft_id is None:
        await message.answer("Usage: /preview_channel <id>")
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            await message.answer("Draft not found.")
            return
    from publisher.draft_media import media_from_extras_json
    from publisher.publish_formatting import build_channel_message_html

    html = build_channel_message_html(
        draft.content or "",
        draft.sources,
        draft_id=draft_id,
        runtime_dir=settings.runtime_state_dir,
    )
    media = media_from_extras_json(draft.extras)
    media_note = ""
    if media:
        try:
            import json as _json

            ex = _json.loads(draft.extras or "{}")
            m = ex.get("media") if isinstance(ex, dict) else {}
            status = m.get("media_status", "?") if isinstance(m, dict) else "?"
            reason = m.get("media_generation_reason", "") if isinstance(m, dict) else ""
            fb = m.get("media_fallback_used", False) if isinstance(m, dict) else False
            media_note = (
                f"\n<i>Медиа:</i> {status} · {media['media_type']}"
                f"{' · fallback' if fb else ''}"
                f"{(' · ' + str(reason)[:60]) if reason else ''}"
            )
        except Exception:
            media_note = f"\n<i>Медиа:</i> {media['media_type']}"
    else:
        media_note = "\n<i>Медиа:</i> text_only"
    header = f"<b>Превью канала · черновик #{draft_id}</b>{media_note}\n\n"
    full = header + html
    if len(full) > 3800:
        full = full[:3780] + "\n<i>…truncated</i>"
    if media and Path(media["local_path"]).is_file():
        from aiogram.types import FSInputFile

        upload = FSInputFile(media["local_path"])
        cap = full if len(full) <= 1024 else full[:1000] + "…"
        if media["media_type"] == "photo":
            await message.answer_photo(upload, caption=cap, parse_mode=ParseMode.HTML)
        else:
            await message.answer_video(upload, caption=cap, parse_mode=ParseMode.HTML)
        return
    await message.answer(full, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@router.message(Command("approve"))
async def cmd_approve(message: Message, bot: Bot, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    draft_id = _parse_slash_command_int("approve", message.text)
    if draft_id is None:
        await message.answer("Usage: /approve <id>")
        return
    res = await _admin_publish_draft_flow(
        bot,
        settings,
        draft_id,
        bypass_cadence=True,
        bypass_leadership=True,
        operator_override=True,
    )
    if res.outcome is _PublishFlowOutcome.MISSING:
        await message.answer("Draft not found.")
        return
    if res.outcome is _PublishFlowOutcome.DRY_RUN:
        await message.answer(
            f"DRY RUN: would publish draft #{draft_id} (no channel send, DB unchanged).",
            disable_web_page_preview=True,
        )
        return
    if res.outcome is _PublishFlowOutcome.ALREADY_HANDLED:
        await message.answer("Already handled or in progress.")
        return
    if res.outcome is _PublishFlowOutcome.APPROVE_DENIED:
        await message.answer("Cannot approve this draft (wrong status).")
        return
    if res.outcome is _PublishFlowOutcome.CADENCE_DEFERRED:
        await message.answer(
            "Publication cadence / quiet-hours gate: try again later.\n"
            + (f"Details: {(res.error or '')[:400]}" if res.error else ""),
            disable_web_page_preview=True,
        )
        return
    if res.outcome is _PublishFlowOutcome.SEND_FAILED:
        await message.answer("Publish failed (see logs).")
        return
    if res.outcome is _PublishFlowOutcome.FINALIZE_MISMATCH:
        await message.answer("State conflict after channel send — check DB and channel.")
        return
    try:
        from app.editorial.operator_feedback import receive_operator_feedback
        from utils.operational_context import current_tick_id

        await receive_operator_feedback(
            settings=settings,
            operator_id=int(message.from_user.id),
            action="approve",
            tick_id=current_tick_id() or "",
            draft_id=draft_id,
            metadata={"channel_message_id": res.channel_message_id},
        )
    except Exception:
        pass
    await message.answer(f"Published draft #{draft_id} (channel msg {res.channel_message_id}).")


@router.message(Command("reject"))
async def cmd_reject(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    draft_id = _parse_slash_command_int("reject", message.text)
    if draft_id is None:
        await message.answer("Usage: /reject <id>")
        return
    async with session_scope() as session:
        ok = await reject_draft(session, draft_id)
        draft = await get_draft_by_id(session, draft_id)
        content = draft.content if draft else ""
        status = draft.status if draft else ""
    if not ok:
        await message.answer("Cannot reject this draft (wrong status).")
        return
    log_event(logger, "draft.rejected_command", draft_id=draft_id, status=status)
    try:
        from app.editorial.operator_feedback import receive_operator_feedback
        from utils.operational_context import current_tick_id

        chans: list[str] = []
        try:
            src = json.loads((draft.sources if draft else None) or "[]")
            if isinstance(src, list):
                chans = [str(s.get("channel") or "") for s in src if isinstance(s, dict)]
        except (json.JSONDecodeError, TypeError):
            pass
        await receive_operator_feedback(
            settings=settings,
            operator_id=int(message.from_user.id),
            action="reject",
            tick_id=current_tick_id() or "",
            draft_id=draft_id,
            metadata={"channels": chans, "status": status},
        )
    except Exception:
        pass
    await message.answer(
        f"Rejected draft #{draft_id}.\nPreview:\n{(content or '')[:400]}",
        disable_web_page_preview=True,
    )


@router.message(Command("edit_title"))
async def cmd_edit_title(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    pr = _parse_id_and_rest("edit_title", message.text)
    if not pr:
        await message.answer("Usage: /edit_title <id> <new title>")
        return
    did, title = pr
    async with session_scope() as session:
        ok = await update_draft_title(session, did, title=title)
    if not ok:
        await message.answer("Update failed (empty, wrong status, or draft missing).")
        return
    await message.answer(f"Title updated for draft #{did}.")


@router.message(Command("edit_summary"))
async def cmd_edit_summary(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    pr = _parse_id_and_rest("edit_summary", message.text)
    if not pr:
        await message.answer("Usage: /edit_summary <id> <text>")
        return
    did, summary = pr
    async with session_scope() as session:
        ok = await update_draft_summary(session, did, summary=summary)
    if not ok:
        await message.answer("Update failed (empty, wrong status, or draft missing).")
        return
    await message.answer(f"Summary updated for draft #{did}.")


async def _cmd_rewrite_mode(message: Message, settings: Settings, mode: str) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    cmd = f"rewrite_{mode}"
    draft_id = _parse_slash_command_int(cmd, message.text)
    if draft_id is None:
        await message.answer(f"Usage: /{cmd} <id>")
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            await message.answer("Draft not found.")
            return
        new_content = rewrite_draft(draft.content or "", mode)  # type: ignore[arg-type]
        ok = await update_draft_content(session, draft_id, content=new_content)
        if not ok:
            await message.answer("Rewrite failed (empty or wrong status).")
            return
        try:
            cur = json.loads(draft.draft_extras or "{}")
        except (json.JSONDecodeError, TypeError):
            cur = {}
        if not isinstance(cur, dict):
            cur = {}
        rw = cur.get("rewrite_suggestions") if isinstance(cur.get("rewrite_suggestions"), dict) else {}
        rw = dict(rw)
        rw[mode] = new_content[:900]
        await merge_draft_extras(session, draft_id, {"rewrite_suggestions": rw})
    await message.answer(f"Draft #{draft_id} rewritten ({mode}). Preview with /draft {draft_id}.")


@router.message(Command("rewrite_short"))
async def cmd_rewrite_short(message: Message, settings: Settings) -> None:
    await _cmd_rewrite_mode(message, settings, "short")


@router.message(Command("rewrite_formal"))
async def cmd_rewrite_formal(message: Message, settings: Settings) -> None:
    await _cmd_rewrite_mode(message, settings, "formal")


@router.message(Command("rewrite_urgent"))
async def cmd_rewrite_urgent(message: Message, settings: Settings) -> None:
    await _cmd_rewrite_mode(message, settings, "urgent")


@router.message(Command("retitle"))
async def cmd_retitle(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    draft_id = _parse_slash_command_int("retitle", message.text)
    if draft_id is None:
        await message.answer("Usage: /retitle <id>")
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            await message.answer("Draft not found.")
            return
        content = draft.content or ""
        editor_title = draft.editor_title
        base = generate_title_suggestions(content, editor_title=editor_title)
        titles = await apply_optional_title_enhancement(None, base=base, content=content)
        await merge_draft_extras(session, draft_id, {"title_suggestions": titles})
    lines = [
        f"Title suggestions for #{draft_id}:",
        f"• short: {titles.get('short_title', '')}",
        f"• standard: {titles.get('standard_title', '')}",
        f"• urgent: {titles.get('urgent_title', '')}",
    ]
    text = "\n".join(lines)
    if len(text) > 3500:
        text = text[:3490] + "\n…"
    await message.answer(text, disable_web_page_preview=True)


@router.message(Command("schedule"))
async def cmd_schedule(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    pr = _parse_schedule_command(message.text)
    if not pr:
        await message.answer("Usage: /schedule <id> <time> (e.g. 18:30 or 2026-05-15T18:30:00Z)")
        return
    did, time_part = pr
    when = parse_draft_schedule_at(time_part, now=utcnow(), tz_name=settings.newsroom_timezone)
    if when is None:
        await message.answer("Could not parse time. Use HH:MM or ISO datetime.")
        return
    async with session_scope() as session:
        ok = await schedule_draft_publish(session, did, when=when)
    if not ok:
        await message.answer("Schedule failed (wrong status or draft missing). Note: auto-publish runs only for APPROVED drafts at due time.")
        return
    await message.answer(f"Draft #{did} scheduled for {when.isoformat()} (UTC).")


@router.message(Command("scheduled"))
async def cmd_scheduled(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    async with session_scope() as session:
        rows = await list_scheduled_drafts(session, limit=40)
    if not rows:
        await message.answer("No scheduled drafts.")
        return
    lines = []
    for d in rows:
        at = d.scheduled_publish_at.isoformat() if d.scheduled_publish_at else "?"
        lines.append(f"#{d.id}\t{d.status}\t{at}")
    await message.answer("\n".join(lines), disable_web_page_preview=True)


@router.callback_query(F.data.startswith("qpage:"))
async def on_queue_page(callback: CallbackQuery, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return
    try:
        parts = (callback.data or "").split(":")
        if len(parts) >= 3:
            page = int(parts[1])
            mode = parts[2]
        else:
            page = int(parts[1])
            mode = "fifo"
    except (ValueError, IndexError):
        await callback_ack(callback, "Bad page", show_alert=True)
        return
    body, has_next, _ = await _queue_page_content(settings, page=page, mode=mode)
    kb = queue_pagination_keyboard(page=page, has_next=has_next, mode=mode)
    await callback.message.answer(
        body,
        reply_markup=kb if kb.inline_keyboard else None,
        disable_web_page_preview=True,
    )
    await callback_ack(callback)


@router.callback_query(F.data.startswith("schtip:"))
async def on_schedule_tip(callback: CallbackQuery, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return
    await callback_ack(callback, "Команда: /schedule <id> ЧЧ:ММ или ISO-время", show_alert=True)


@router.callback_query(F.data.startswith("rett:"))
async def on_suggest_title(callback: CallbackQuery, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return
    draft_id = _parse_callback_draft_id(callback.data)
    if draft_id is None:
        await callback_ack(callback, "Invalid payload", show_alert=True)
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            await callback_ack(callback, "Draft missing", show_alert=True)
            return
        content = draft.content or ""
        base = generate_title_suggestions(content, editor_title=draft.editor_title)
        titles = await apply_optional_title_enhancement(None, base=base, content=content)
        await merge_draft_extras(session, draft_id, {"title_suggestions": titles})
    lines = [
        f"Варианты заголовка #{draft_id}:",
        f"• короткий: {titles.get('short_title', '')}",
        f"• стандартный: {titles.get('standard_title', '')}",
        f"• срочный: {titles.get('urgent_title', '')}",
    ]
    text = "\n".join(lines)
    if callback.message is not None:
        await callback.message.answer(text[:3500], disable_web_page_preview=True)
    await callback_ack(callback, "Stored suggestions")


@router.callback_query(F.data.startswith("pre:"))
async def on_preview(callback: CallbackQuery, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return
    draft_id = _parse_callback_draft_id(callback.data)
    if draft_id is None:
        await callback_ack(callback, "Invalid payload", show_alert=True)
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
        if draft is None:
            await callback_ack(callback, "Draft missing", show_alert=True)
            return
        intel = await draft_duplicate_intel(
            session,
            draft_id,
            similarity_threshold=settings.draft_similarity_threshold,
        )
    html = render_internal_review_html(
        draft_id,
        draft.content or "",
        draft.sources,
        editor_title=draft.editor_title,
        editor_summary=draft.editor_summary,
        draft_extras_json=_extras_json_for_preview(draft, settings),
        status=draft.status,
        created_at_iso=draft.created_at.isoformat() if draft.created_at else "",
        scheduled_at_iso=draft.scheduled_publish_at.isoformat() if draft.scheduled_publish_at else None,
        duplicate_intel=intel,
    )
    if callback.message is not None:
        await callback.message.answer(html, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await callback_ack(callback)


@router.callback_query(F.data.startswith("retry:"))
async def on_retry_publish(callback: CallbackQuery, bot: Bot, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return
    draft_id = _parse_callback_draft_id(callback.data)
    if draft_id is None:
        await callback_ack(callback, "Invalid payload", show_alert=True)
        return
    res = await _admin_publish_draft_flow(
        bot,
        settings,
        draft_id,
        bypass_cadence=True,
        bypass_leadership=True,
        operator_override=True,
    )
    if res.outcome is _PublishFlowOutcome.MISSING:
        await callback_ack(callback, "Draft missing", show_alert=True)
        return
    if res.outcome is _PublishFlowOutcome.DRY_RUN:
        await callback_ack(callback, "Dry run", show_alert=True)
        return
    if res.outcome is _PublishFlowOutcome.ALREADY_HANDLED:
        await callback_ack(callback, "Already handled")
        return
    if res.outcome is _PublishFlowOutcome.APPROVE_DENIED:
        await callback_ack(callback, "Cannot publish", show_alert=True)
        return
    if res.outcome is _PublishFlowOutcome.CADENCE_DEFERRED:
        await callback_ack(callback, "Cadence / quiet hours — retry later", show_alert=True)
        return
    if res.outcome is _PublishFlowOutcome.SEND_FAILED:
        await callback_ack(callback, "Publish failed", show_alert=True)
        return
    if res.outcome is _PublishFlowOutcome.FINALIZE_MISMATCH:
        await callback_ack(callback, "State conflict", show_alert=True)
        return
    await _edit_admin_draft_footer(
        callback.message,
        draft_id=draft_id,
        content=res.draft_content,
        sources=res.draft_sources,
        footer_html="<b>Status:</b> published ✅",
    )
    await callback_ack(callback, "Published")


@router.callback_query(F.data.startswith("pub:"))
async def on_publish(callback: CallbackQuery, bot: Bot, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return

    draft_id = _parse_callback_draft_id(callback.data)
    if draft_id is None:
        await callback_ack(callback, "Invalid payload", show_alert=True)
        return

    await callback_ack(callback)
    res = await _admin_publish_draft_flow(
        bot,
        settings,
        draft_id,
        bypass_cadence=True,
        bypass_leadership=True,
        operator_override=True,
    )

    if res.outcome is _PublishFlowOutcome.MISSING:
        await _callback_user_feedback(callback, "Draft not found.")
        return

    if res.outcome is _PublishFlowOutcome.DRY_RUN:
        await _edit_admin_draft_footer(
            callback.message,
            draft_id=draft_id,
            content=res.draft_content,
            sources=res.draft_sources,
            footer_html="<b>DRY RUN</b>: publish to channel skipped.",
        )
        await _callback_user_feedback(callback, "Dry run: not published to channel.")
        return

    if res.outcome is _PublishFlowOutcome.ALREADY_HANDLED:
        await _strip_markup_safe(callback.message)
        await _callback_user_feedback(callback, "Already handled.")
        return

    if res.outcome is _PublishFlowOutcome.APPROVE_DENIED:
        await _callback_user_feedback(callback, "Cannot approve this draft.")
        return

    if res.outcome is _PublishFlowOutcome.CADENCE_DEFERRED:
        await _callback_user_feedback(callback, "Cadence / quiet hours — retry later.")
        return

    if res.outcome is _PublishFlowOutcome.SEND_FAILED:
        await _callback_user_feedback(callback, f"Publish failed: {(res.error or 'check logs')[:400]}")
        return

    if res.outcome is _PublishFlowOutcome.FINALIZE_MISMATCH:
        await _callback_user_feedback(callback, "State conflict — check channel for duplicate posts.")
        return

    await _edit_admin_draft_footer(
        callback.message,
        draft_id=draft_id,
        content=res.draft_content,
        sources=res.draft_sources,
        footer_html="<b>Status:</b> published ✅",
    )


@router.callback_query(F.data.startswith("rej:"))
async def on_reject(callback: CallbackQuery, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return

    draft_id = _parse_callback_draft_id(callback.data)
    if draft_id is None:
        await callback_ack(callback, "Invalid payload", show_alert=True)
        return

    await callback_ack(callback)
    draft_content = ""
    draft_sources = ""

    async with session_scope() as session:
        ok = await reject_draft(session, draft_id)
        draft = await get_draft_by_id(session, draft_id)
        if draft:
            draft_content = draft.content or ""
            draft_sources = draft.sources or ""

    if not ok:
        await _callback_user_feedback(callback, "Cannot reject this draft.")
        return

    log_event(logger, "draft.rejected", draft_id=draft_id)

    await _edit_admin_draft_footer(
        callback.message,
        draft_id=draft_id,
        content=draft_content,
        sources=draft_sources,
        footer_html="<b>Status:</b> rejected ⛔️",
    )


@router.message(Command("explain"))
async def cmd_explain(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    draft_id = _parse_slash_command_int("explain", message.text)
    if draft_id is None:
        await message.answer("Usage: /explain <id>")
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
    if draft is None:
        await message.answer("Draft not found.")
        return
    try:
        ex = json.loads(draft.draft_extras or "{}")
    except (json.JSONDecodeError, TypeError):
        ex = {}
    out = explain_from_draft_extras(ex if isinstance(ex, dict) else {})
    sup = explain_suppression(ex if isinstance(ex, dict) else {})
    t1 = (out.get("concise") or "")[:3500]
    t2 = ((out.get("detailed") or "")[:2800] + "\n\n— Suppression —\n" + sup)[:3800]
    await message.answer(t1 or "No explanation.", disable_web_page_preview=True)
    if t2.strip():
        await message.answer(t2, disable_web_page_preview=True)


@router.message(Command("diff"))
async def cmd_diff(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    draft_id = _parse_slash_command_int("diff", message.text)
    if draft_id is None:
        await message.answer("Usage: /diff <id>")
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
    if draft is None:
        await message.answer("Draft not found.")
        return
    dif = headline_and_lead_diff(
        draft_content=draft.content or "",
        editor_title=draft.editor_title,
        editor_summary=draft.editor_summary,
    )
    body = ((dif.get("title_diff") or "").strip() + "\n" + (dif.get("summary_diff") or "").strip()).strip()
    hist = format_edit_history(getattr(draft, "edit_history", None) or "[]")
    msg = (body or "(no title/summary diff — editor fields empty)") + "\n\n— edit_history —\n" + (hist[:2800] or "(empty)")
    await message.answer(msg[:3900], disable_web_page_preview=True)


@router.message(Command("note"))
async def cmd_note(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    pr = _parse_id_and_rest("note", message.text)
    if not pr:
        await message.answer("Usage: /note <id> <text>")
        return
    did, note = pr
    async with session_scope() as session:
        ok = await merge_draft_extras(session, did, {"moderation_note": note[:4000]})
    if not ok:
        await message.answer("Draft not found.")
        return
    await message.answer(f"Moderation note saved on draft #{did}.")


@router.message(Command("policy_override"))
async def cmd_policy_override(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    pr = _parse_id_and_rest("policy_override", message.text)
    if not pr:
        await message.answer("Usage: /policy_override <id> <reason>")
        return
    did, reason = pr
    async with session_scope() as session:
        ok = await merge_draft_extras(session, did, {"policy_override_reason": reason[:4000]})
    if not ok:
        await message.answer("Draft not found.")
        return
    await message.answer(f"Policy override reason recorded for draft #{did}.")


@router.message(Command("find"))
async def cmd_find(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    kv = _parse_find_command(message.text)
    if not kv:
        await message.answer(
            "Usage: /find topic:substring entity:x fingerprint:abc123 suppression:reason status:pending",
            disable_web_page_preview=True,
        )
        return
    async with session_scope() as session:
        rows = await search_drafts_operational(
            session,
            topic_substr=kv.get("topic"),
            entity_substr=kv.get("entity"),
            fingerprint_substr=kv.get("fingerprint"),
            suppression_reason_substr=kv.get("suppression"),
            status=kv.get("status"),
            limit=25,
        )
    if not rows:
        await message.answer("No matches.")
        return
    lines = []
    for d in rows:
        head = (d.content or "").splitlines()[0][:100] if (d.content or "").splitlines() else ""
        lines.append(f"#{d.id} [{d.status}] {head}")
    await message.answer("\n".join(lines)[:3900], disable_web_page_preview=True)


@router.callback_query(F.data.startswith("exp:"))
async def on_explain_callback(callback: CallbackQuery, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return
    draft_id = _parse_callback_draft_id(callback.data)
    if draft_id is None:
        await callback_ack(callback, "Invalid payload", show_alert=True)
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
    if draft is None:
        await callback_ack(callback, "Draft missing", show_alert=True)
        return
    try:
        ex = json.loads(draft.draft_extras or "{}")
    except (json.JSONDecodeError, TypeError):
        ex = {}
    out = explain_from_draft_extras(ex if isinstance(ex, dict) else {})
    preview = (out.get("concise") or "")[:900]
    if callback.message:
        await callback.message.answer(preview or "No explanation.", disable_web_page_preview=True)
    await callback_ack(callback, "Explanation sent")


@router.callback_query(F.data.startswith("diff:"))
async def on_diff_callback(callback: CallbackQuery, settings: Settings) -> None:
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return
    draft_id = _parse_callback_draft_id(callback.data)
    if draft_id is None:
        await callback_ack(callback, "Invalid payload", show_alert=True)
        return
    async with session_scope() as session:
        draft = await get_draft_by_id(session, draft_id)
    if draft is None:
        await callback_ack(callback, "Draft missing", show_alert=True)
        return
    dif = headline_and_lead_diff(
        draft_content=draft.content or "",
        editor_title=draft.editor_title,
        editor_summary=draft.editor_summary,
    )
    body = ((dif.get("title_diff") or "").strip() + "\n" + (dif.get("summary_diff") or "").strip()).strip() or "(empty)"
    if callback.message:
        await callback.message.answer(body[:3500], disable_web_page_preview=True)
    await callback_ack(callback, "Diff sent")


def _moderation_notify_chat_id(settings: Settings) -> int:
    """Chat where draft approval keyboards are delivered (private admin DM by default)."""
    if settings.moderation_chat_id is not None:
        return int(settings.moderation_chat_id)
    return int(settings.admin_user_id)


async def notify_admin_new_draft(
    bot: Bot,
    settings: Settings,
    *,
    draft_id: int,
    content: str,
    sources: str,
    editorial_intelligence: dict[str, object] | None = None,
    draft_extras_json: str | None = None,
) -> None:
    from app.ops.autonomous_publish import autonomous_editorial_mode_enabled

    if autonomous_editorial_mode_enabled():
        log_event(
            logger,
            "draft.autonomous_skip_moderation_notify",
            draft_id=draft_id,
        )
        return

    from pathlib import Path

    from aiogram.types import FSInputFile

    from publisher.draft_media import media_from_extras_json

    notify_chat = _moderation_notify_chat_id(settings)
    html_body = render_internal_review_html(
        draft_id,
        content,
        sources,
        draft_extras_json=draft_extras_json,
        status=DraftStatus.PENDING.value,
        editorial_intelligence=editorial_intelligence,
    )
    media = media_from_extras_json(draft_extras_json)
    keyboard = draft_actions_keyboard(draft_id, status=DraftStatus.PENDING.value)
    if media and Path(media["local_path"]).is_file():
        upload = FSInputFile(media["local_path"])
        # Photo/video captions: plain text only (HTML captions break on truncation).
        short_caption = f"Draft #{draft_id} — на модерации"
        if media["media_type"] == "photo":
            mid = await send_channel_photo(
                bot,
                photo=upload,
                chat_id=notify_chat,
                caption=short_caption,
                draft_id=draft_id,
            )
        else:
            mid = await send_channel_video(
                bot,
                video=upload,
                chat_id=notify_chat,
                caption=short_caption,
                draft_id=draft_id,
            )
        async with session_scope() as session:
            await set_draft_admin_message(session, draft_id, int(mid))
        if len(html_body) <= SAFE_CHUNK:
            msg = await bot.send_message(
                chat_id=notify_chat,
                text=html_body,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )
            async with session_scope() as session:
                await set_draft_admin_message(session, draft_id, int(msg.message_id))
        else:
            parts = split_telegram_text(html_body, respect_html=True)
            last_id: int | None = None
            for idx, part in enumerate(parts):
                is_last = idx == len(parts) - 1
                msg = await bot.send_message(
                    chat_id=notify_chat,
                    text=part,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard if is_last else None,
                    disable_web_page_preview=True,
                )
                last_id = int(msg.message_id)
            if last_id is not None:
                async with session_scope() as session:
                    await set_draft_admin_message(session, draft_id, last_id)
        log_event(logger, "draft.admin_notified", draft_id=draft_id, parts=1, with_media=True)
        return
    if len(html_body) <= SAFE_CHUNK:
        msg = await bot.send_message(
            chat_id=notify_chat,
            text=html_body,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
        async with session_scope() as session:
            await set_draft_admin_message(session, draft_id, int(msg.message_id))
        log_event(logger, "draft.admin_notified", draft_id=draft_id, parts=1)
        return

    header_plain = f"Draft #{draft_id} (split: HTML preview too long)\n\n"
    body_plain = f"{content}\n\nSources JSON:\n{sources}\n"
    full_plain = header_plain + body_plain
    parts = split_telegram_text(full_plain)
    last_id: int | None = None
    for idx, part in enumerate(parts):
        is_last = idx == len(parts) - 1
        msg = await bot.send_message(
            chat_id=notify_chat,
            text=part,
            parse_mode=ParseMode.HTML if is_last else None,
            reply_markup=draft_actions_keyboard(draft_id, status=DraftStatus.PENDING.value) if is_last else None,
            disable_web_page_preview=True,
        )
        last_id = int(msg.message_id)
        if idx < len(parts) - 1 and settings.telegram_inter_chunk_delay_sec > 0:
            await asyncio.sleep(settings.telegram_inter_chunk_delay_sec)

    if last_id is not None:
        async with session_scope() as session:
            await set_draft_admin_message(session, draft_id, last_id)
    log_event(logger, "draft.admin_notified", draft_id=draft_id, parts=len(parts))


@router.message(Command("editorial_freeze"))
async def cmd_editorial_freeze(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    from editorial.governance.operator_controls import set_emergency_freeze

    parts = (message.text or "").split(maxsplit=1)
    on = len(parts) < 2 or parts[1].strip().lower() in ("on", "1", "true", "yes")
    reason = parts[1] if len(parts) > 1 and parts[1].strip().lower() not in ("on", "off", "0", "false") else ""
    set_emergency_freeze(settings.runtime_state_dir, enabled=on, reason=reason)
    await message.answer(f"Emergency editorial freeze: {'ON' if on else 'OFF'}")


@router.message(Command("mute_source"))
async def cmd_mute_source(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /mute_source <channel> [minutes]")
        return
    from editorial.governance.operator_controls import mute_source

    mins = float(parts[2]) if len(parts) > 2 else 60.0
    mute_source(settings.runtime_state_dir, parts[1], ttl_sec=mins * 60.0, reason="operator_command")
    await message.answer(f"Muted source {parts[1]} for {mins:.0f} min.")


@router.message(Command("boost_source"))
async def cmd_boost_source(message: Message, settings: Settings) -> None:
    if not _admin_private_message(message, settings):
        await message.answer("Access denied.")
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Usage: /boost_source <channel> [boost 0.05-0.2]")
        return
    from editorial.governance.operator_controls import boost_source

    boost = float(parts[2]) if len(parts) > 2 else 0.08
    boost_source(settings.runtime_state_dir, parts[1], boost=boost, reason="operator_command")
    await message.answer(f"Boosted source {parts[1]} by {boost:.3f}.")


@_fallback_router.callback_query()
async def on_unhandled_callback(callback: CallbackQuery, settings: Settings) -> None:
    """Catch-all so Telegram never leaves a spinner on unknown/expired buttons."""
    if not _admin_private_approval(callback, settings):
        await callback_ack(callback, "Access denied", show_alert=True)
        return
    log_event(logger, "bot.callback.unhandled", data=(callback.data or "")[:64])
    await callback_ack(callback, "Action not available", show_alert=True)


def register_handlers(dp: Dispatcher, settings: Settings) -> None:
    from bot.operator_ops_commands import router as ops_router

    router.message.middleware(SafeHandlerMiddleware())
    router.message.middleware(SettingsMiddleware(settings))
    router.callback_query.middleware(SettingsMiddleware(settings))
    router.callback_query.middleware(SafeCallbackMiddleware())
    _fallback_router.callback_query.middleware(SettingsMiddleware(settings))
    _fallback_router.callback_query.middleware(SafeCallbackMiddleware())
    ops_router.message.middleware(SafeHandlerMiddleware())
    ops_router.message.middleware(SettingsMiddleware(settings))
    dp.include_router(router)
    dp.include_router(ops_router)
    dp.include_router(_fallback_router)
