from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

from publisher.operator_ui_ru import (
    format_source_line,
    tr_draft_status,
    tr_duplicate_severity,
    tr_moderation_hint,
    tr_priority_level,
    tr_quality_metric,
    tr_reasoning_line,
    tr_scoring_reason,
    tr_yes_no,
)
from utils.telegram_html import escape_telegram_html


def _first_line_title(content: str) -> str:
    lines = [ln.strip() for ln in content.strip().splitlines() if ln.strip()]
    if not lines:
        return "Черновик"
    first = lines[0]
    if len(first) > 120:
        return first[:117] + "…"
    return first


def _sources_lines(sources: str | list[dict[str, Any]] | None, *, max_items: int = 12) -> list[str]:
    if sources is None:
        return []
    if isinstance(sources, list):
        items = sources[:max_items]
        out: list[str] = []
        for it in items:
            out.append(f"- {format_source_line(str(it.get('channel', '?')), it.get('message_id', '?'))}")
        return out
    try:
        data = json.loads(sources)
    except (json.JSONDecodeError, TypeError):
        return [f"- {escape_telegram_html(str(sources)[:200])}"]
    if not isinstance(data, list):
        return [f"- {escape_telegram_html(str(data)[:200])}"]
    return _sources_lines(data, max_items=max_items)


def render_draft_preview(
    draft_id: int,
    content: str,
    sources: str | list[dict[str, Any]] | None,
    *,
    title: str | None = None,
    max_chars: int = 3500,
) -> str:
    """Plain-text preview for moderation (deterministic, Telegram-safe plain text)."""
    ttl = title or _first_line_title(content)
    ttl = re.sub(r"[\r\n]+", " ", ttl).strip() or "Черновик"
    body = content.strip()
    if len(body) > max_chars - 400:
        body = body[: max_chars - 420] + "\n…"

    lines = [
        f"📰 {ttl}",
        "",
        body,
        "",
        "Источники:",
    ]
    lines.extend(_sources_lines(sources))
    lines.extend(["", f"ID черновика: {int(draft_id)}"])
    out = "\n".join(lines).strip()
    if len(out) > max_chars:
        out = out[: max_chars - 3] + "…"
    return out


def render_draft_preview_html(
    draft_id: int,
    content: str,
    sources: str | list[dict[str, Any]] | None,
    *,
    title: str | None = None,
    max_chars: int = 3500,
) -> str:
    plain = render_draft_preview(draft_id, content, sources, title=title, max_chars=max_chars)
    safe = escape_telegram_html(plain)
    return f"<pre>{safe}</pre>"


def _extras_dict(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _hashtag_from_content(content: str, *, limit: int = 8) -> list[str]:
    tags = sorted(set(re.findall(r"#[\w\u0400-\u04FF]{2,32}", content or "", flags=re.UNICODE)))
    return tags[:limit]


def render_rich_draft_preview_html(
    draft_id: int,
    content: str,
    sources: str | list[dict[str, Any]] | None,
    *,
    editor_title: str | None = None,
    editor_summary: str | None = None,
    draft_extras_json: str | None = None,
    status: str = "pending",
    created_at_iso: str = "",
    scheduled_at_iso: str | None = None,
    publish_warnings: list[str] | None = None,
    duplicate_intel: dict[str, Any] | None = None,
    max_chars: int = 3800,
) -> str:
    """
    Rich Telegram HTML preview (subset: b, i, code, blockquote, pre); deterministic truncation.
    """
    from app.publisher.draft_builder import finalize_draft_content

    display_content = finalize_draft_content(content or "", max_chars=3500)
    extras = _extras_dict(draft_extras_json)
    quality = extras.get("quality") if isinstance(extras.get("quality"), dict) else {}
    dup = duplicate_intel if isinstance(duplicate_intel, dict) else extras.get("duplicate_intel")
    if not isinstance(dup, dict):
        dup = {}
    title = (editor_title or "").strip() or _first_line_title(display_content)
    title = escape_telegram_html(re.sub(r"[\r\n]+", " ", title).strip() or "Черновик")
    summary = (editor_summary or "").strip()
    if not summary:
        lines = [ln.strip() for ln in display_content.splitlines() if ln.strip()]
        summary = "\n".join(lines[:5]) if lines else display_content.strip()
    summary = escape_telegram_html(summary.strip())
    if len(summary) > 900:
        summary = summary[:880] + "…"

    parts: list[str] = [f"📰 <b>{title}</b>", "", f"<i>{summary}</i>"]

    intel = extras.get("editorial_intelligence") if isinstance(extras.get("editorial_intelligence"), dict) else {}
    if intel:
        from editorial.scoring.preview import render_editorial_intelligence_html

        block = render_editorial_intelligence_html(intel)
        if block:
            parts.append(block)
    elif quality:
        parts.extend(["", "<b>Качество</b>"])
        for k in sorted(quality.keys()):
            if k.endswith("_raw"):
                continue
            v = quality[k]
            label = escape_telegram_html(tr_quality_metric(str(k)))
            parts.append(f"• <code>{label}</code>: {escape_telegram_html(str(v))}")

    sev = str(dup.get("severity") or "none")
    max_pct = dup.get("max_similarity_pct")
    parts.extend(
        ["", "<b>Дубликаты</b>", f"• степень: <code>{escape_telegram_html(tr_duplicate_severity(sev))}</code>"]
    )
    if max_pct is not None:
        parts.append(f"• макс. схожесть: <code>{escape_telegram_html(str(max_pct))}%</code>")
    rel = dup.get("related") if isinstance(dup.get("related"), list) else []
    for item in sorted(rel, key=lambda x: (-float(x.get("similarity_pct", 0)), int(x.get("draft_id", 0))))[:6]:
        if not isinstance(item, dict):
            continue
        did = int(item.get("draft_id", 0))
        pct = item.get("similarity_pct", "")
        parts.append(f"• #{did} — {escape_telegram_html(str(pct))}%")

    src_lines = _sources_lines(sources, max_items=10)
    if src_lines:
        parts.extend(["", "<b>Источники</b>"])
        for ln in src_lines:
            parts.append(f"• {escape_telegram_html(ln.lstrip('- '))}")

    tags = extras.get("tags") if isinstance(extras.get("tags"), list) else []
    if not tags:
        tags = _hashtag_from_content(display_content)
    inf_tags = extras.get("inferred_tags")
    if isinstance(inf_tags, list):
        tags = sorted(set([str(t) for t in tags] + [str(t) for t in inf_tags if t]))[:16]
    tags = [str(t) for t in tags][:12]
    if tags:
        parts.extend(["", "<b>Теги</b>", escape_telegram_html(" ".join(sorted(tags)))])

    cat = extras.get("category")
    if isinstance(cat, str) and cat.strip():
        parts.extend(["", f"<b>Категория</b>: {escape_telegram_html(cat.strip())}"])

    cconf = extras.get("category_confidence")
    if cconf is not None:
        parts.append(f"<b>Уверенность в категории</b>: <code>{escape_telegram_html(str(cconf))}</code>")
    creason = extras.get("category_reasoning")
    if isinstance(creason, str) and creason.strip():
        parts.append(f"<i>{escape_telegram_html(tr_scoring_reason(creason.strip())[:320])}</i>")

    kw = extras.get("keywords_matched")
    if isinstance(kw, list) and kw:
        parts.append(f"<b>Ключевые слова</b> ({len(kw)}): {escape_telegram_html(', '.join(str(x) for x in kw[:8]))}")

    pri = extras.get("priority") if isinstance(extras.get("priority"), dict) else {}
    if pri:
        lvl = str(pri.get("priority_level") or "")
        nscore = pri.get("numeric_priority_score")
        parts.extend(
            [
                "",
                "<b>Приоритет</b>",
                f"• уровень: <code>{escape_telegram_html(tr_priority_level(lvl))}</code>"
                + (f" • балл: <code>{escape_telegram_html(str(nscore))}</code>" if nscore is not None else ""),
            ]
        )
        hint = pri.get("moderation_hint")
        if isinstance(hint, str) and hint.strip():
            parts.append(f"• подсказка: {escape_telegram_html(tr_moderation_hint(hint.strip())[:280])}")
        rs = pri.get("reasoning")
        if isinstance(rs, str) and rs.strip():
            parts.append(f"• <i>{escape_telegram_html(tr_reasoning_line(rs.strip())[:360])}</i>")

    brk = extras.get("breaking") if isinstance(extras.get("breaking"), dict) else {}
    if brk:
        parts.extend(
            [
                "",
                "<b>Срочное</b>",
                f"• флаг: <code>{escape_telegram_html(tr_yes_no(bool(brk.get('is_breaking'))))}</code>"
                f" • балл: <code>{escape_telegram_html(str(brk.get('breaking_score')))}</code>",
            ]
        )
        br = brk.get("reasoning")
        if isinstance(br, str) and br.strip():
            parts.append(f"• <i>{escape_telegram_html(tr_scoring_reason(br.strip())[:280])}</i>")

    rep = extras.get("source_reputation") if isinstance(extras.get("source_reputation"), dict) else {}
    if rep:
        parts.extend(["", "<b>Репутация источников</b>"])
        for ch, row in sorted(rep.items(), key=lambda kv: str(kv[0]))[:6]:
            if not isinstance(row, dict):
                continue
            sc = row.get("score")
            parts.append(f"• {escape_telegram_html(str(ch)[:40])}: <code>{escape_telegram_html(str(sc))}</code>")

    titles = extras.get("title_suggestions") if isinstance(extras.get("title_suggestions"), dict) else {}
    if titles:
        parts.extend(
            [
                "",
                "<b>Варианты заголовка</b>",
                f"• короткий: {escape_telegram_html(str(titles.get('short_title', ''))[:200])}",
                f"• стандартный: {escape_telegram_html(str(titles.get('standard_title', ''))[:220])}",
                f"• срочный: {escape_telegram_html(str(titles.get('urgent_title', ''))[:220])}",
            ]
        )

    rw = extras.get("rewrite_suggestions") if isinstance(extras.get("rewrite_suggestions"), dict) else {}
    if rw:
        from publisher.operator_ui_ru import REWRITE_MODE_RU

        parts.extend(["", "<b>Последняя правка</b>"])
        for mode in ("short", "formal", "urgent", "neutral"):
            if mode in rw and isinstance(rw[mode], str) and rw[mode].strip():
                mode_ru = REWRITE_MODE_RU.get(mode, mode)
                parts.append(
                    f"• <code>{escape_telegram_html(mode_ru)}</code>: {escape_telegram_html(rw[mode].strip()[:220])}"
                )

    if created_at_iso:
        try:
            raw_ts = created_at_iso.replace("Z", "+00:00")
            cdt = datetime.fromisoformat(raw_ts)
            if cdt.tzinfo is None:
                cdt = cdt.replace(tzinfo=timezone.utc)
            age_h = max(0.0, (datetime.now(timezone.utc) - cdt.astimezone(timezone.utc)).total_seconds() / 3600.0)
            if age_h >= 36.0:
                parts.extend(
                    ["", f"<b>Устаревший черновик</b>: ~{escape_telegram_html(str(round(age_h, 1)))} ч в очереди"]
                )
        except Exception:
            pass

    parts.extend(
        [
            "",
            f"<b>Статус</b>: <code>{escape_telegram_html(tr_draft_status(status))}</code>",
            f"<b>Создан</b>: <code>{escape_telegram_html(created_at_iso or '—')}</code>",
        ]
    )
    if scheduled_at_iso:
        parts.append(f"<b>Запланирован</b>: <code>{escape_telegram_html(scheduled_at_iso)}</code>")

    warns = list(publish_warnings or [])
    for w in dup.get("warning_lines") or []:
        if isinstance(w, str) and w.strip():
            warns.append(w.strip())
    if warns:
        parts.extend(["", "<b>Предупреждения к публикации</b>"])
        for w in sorted(set(warns))[:8]:
            parts.append(f"• {escape_telegram_html(tr_scoring_reason(w)[:240])}")

    parts.extend(["", f"<b>ID черновика</b>: <code>{int(draft_id)}</code>"])
    out = "\n".join(parts)
    if len(out) > max_chars:
        out = out[: max_chars - 16] + "\n<i>…обрезано</i>"
    return out
