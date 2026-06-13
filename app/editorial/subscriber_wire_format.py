"""
Subscriber Wire — growth-optimized publish format for RU macro/news Telegram.

Synthesis from reference channels (@cb_economics, @thebell_io, @rbc_news wire) and
2025–2026 Telegram growth playbooks:

- Bold declarative headline (micro-landing page)
- 2–4 sentences in 1–2 short paragraphs — fast scan, high forward rate
- Key numbers in monospace — screenshot / share friendly
- One contextual takeaway (→) when content-specific — not pipeline boilerplate
- Discrete source line — trust signal
- Soft forward nudge on ~25% of high-forward stories — subscriber acquisition

Avoids: 4-block growth labels, hashtags, open loops, generic «Почему это важно».
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from hashlib import md5
from typing import Any

from app.editorial.cb_brief_format import (
    CB_BRIEF_BODY_MAX_CHARS,
    CB_BRIEF_HEADLINE_MAX,
    apply_cb_brief_shape,
    normalize_cb_body,
    normalize_cb_headline,
)
from utils.telegram_html import escape_telegram_html, sanitize_telegram_html_output

_BREAKING = re.compile(r"(?:^|\b)(?:breaking|срочно|urgent|экстрен|молния)\b", re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NUMBER_HIGHLIGHT = re.compile(
    r"(\d+[.,]?\d*\s*(?:%|б\.?\s*п\.?|bp|млрд|млн|тыс\.?|₽|\$|€|bn|mln|тыс))"
    r"|(\d{1,3}(?:\s+\d{3})+\s*(?:₽|\$|€)?)",
    re.I,
)
_TAKEAWAY_MARKERS = re.compile(
    r"(?:это\s+значит|означает|повлияет|сдвинет|усилит|снизит|рост|падени|"
    r"риск|ставк|инфляц|рынк|инвестор|регулятор|ожидани)",
    re.I,
)
_MACRO_RE = re.compile(
    r"(?:инфляц|ставк|цб|фрс|fed|ecb|gdp|cpi|минфин|бюджет)",
    re.I,
)
_MARKET_RE = re.compile(r"(?:акци|индекс|бирж|облигац|нефт|fx|etf|доходност)", re.I)
_CRYPTO_RE = re.compile(r"(?:bitcoin|btc|ethereum|крипт|defi)", re.I)
_GEO_RE = re.compile(r"(?:санкци|геополит|войн|переговор|дипломат)", re.I)


def subscriber_wire_format_enabled() -> bool:
    from app.growth_layer.format.profiles import publish_format_mode

    return publish_format_mode() == "subscriber_wire"


def _story_bucket(text: str) -> str:
    t = (text or "").lower()
    if _CRYPTO_RE.search(t):
        return "crypto"
    if _GEO_RE.search(t):
        return "geo"
    if _MACRO_RE.search(t):
        return "macro"
    if _MARKET_RE.search(t):
        return "market"
    return "general"


def is_breaking_story(text: str, *, growth_meta: dict[str, Any] | None = None) -> bool:
    if growth_meta and growth_meta.get("is_breaking"):
        return True
    cp = (growth_meta or {}).get("channel_product")
    if isinstance(cp, dict) and cp.get("editorial_category") == "breaking":
        return True
    return bool(_BREAKING.search((text or "")[:200]))


def _stable_mod(text: str, n: int) -> int:
    return int(md5((text or "").encode("utf-8")).hexdigest(), 16) % max(1, n)


@dataclass(frozen=True)
class SubscriberWireParts:
    headline: str
    body: str
    takeaway: str
    bucket: str
    breaking: bool

    def to_plain_block(self) -> str:
        parts: list[str] = []
        prefix = "⚡ " if self.breaking else ""
        if self.headline:
            parts.append(f"{prefix}{self.headline}".strip())
        if self.body:
            if parts:
                parts.append("")
            parts.append(self.body)
        if self.takeaway:
            parts.append("")
            parts.append(f"→ {self.takeaway}")
        return "\n".join(parts).strip()


def extract_subscriber_takeaway(
    body: str,
    *,
    why_it_matters: str = "",
    min_score: float = 55.0,
    reference_forward_score: float = 0.0,
) -> str:
    from app.editorial.content_quality import is_generic_insight

    why = (why_it_matters or "").strip()
    if why and len(why) >= 24 and not is_generic_insight(why):
        return why.rstrip(".!? ") + "."

    if reference_forward_score < min_score:
        return ""

    sents = [s.strip() for s in _SENTENCE_SPLIT.split((body or "").strip()) if len(s.strip()) > 20]
    if len(sents) < 2:
        return ""

    candidate = sents[-1]
    if not _TAKEAWAY_MARKERS.search(candidate):
        return ""
    if is_generic_insight(candidate):
        return ""
    if candidate.lower() == sents[0].lower():
        return ""
    if candidate[-1] not in ".!?":
        candidate = f"{candidate}."
    return candidate


def build_subscriber_wire_parts(
    text: str,
    *,
    why_it_matters: str = "",
    growth_meta: dict[str, Any] | None = None,
    max_body_chars: int = CB_BRIEF_BODY_MAX_CHARS,
) -> SubscriberWireParts:
    raw = (text or "").strip()
    breaking = is_breaking_story(raw, growth_meta=growth_meta)
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if len(lines) >= 2 and len(lines[0]) <= CB_BRIEF_HEADLINE_MAX + 20:
        headline, body = apply_cb_brief_shape(lines[0], "\n\n".join(lines[1:]), why_it_matters="")
    else:
        headline, body = apply_cb_brief_shape("", raw, why_it_matters="")

    body = normalize_cb_body(body, max_chars=max_body_chars)
    headline = normalize_cb_headline(headline, body_fallback=body)

    ref_score = 0.0
    if growth_meta:
        try:
            ref_score = float(growth_meta.get("virality_score") or 0)
        except (TypeError, ValueError):
            ref_score = 0.0
        cp = growth_meta.get("channel_product")
        if isinstance(cp, dict) and cp.get("reference_forward_score") is not None:
            ref_score = max(ref_score, float(cp["reference_forward_score"]))

    takeaway = extract_subscriber_takeaway(
        body,
        why_it_matters=why_it_matters,
        reference_forward_score=ref_score,
    )
    if takeaway:
        sents = [s.strip() for s in _SENTENCE_SPLIT.split(body) if s.strip()]
        if sents and takeaway.rstrip(".!? ").lower() in sents[-1].lower():
            body = " ".join(sents[:-1]).strip()
            if body:
                body = normalize_cb_body(body, max_chars=max_body_chars)

    bucket = _story_bucket(f"{headline}\n{body}")
    return SubscriberWireParts(
        headline=headline,
        body=body,
        takeaway=takeaway,
        bucket=bucket,
        breaking=breaking,
    )


def compose_subscriber_wire_text(
    text: str,
    *,
    max_chars: int = CB_BRIEF_BODY_MAX_CHARS + CB_BRIEF_HEADLINE_MAX + 120,
    growth_meta: dict[str, Any] | None = None,
) -> str:
    parts = build_subscriber_wire_parts(text, growth_meta=growth_meta)
    out = parts.to_plain_block()
    if len(out) > max_chars:
        from app.publisher.draft_builder import complete_story_text

        out = complete_story_text(out, max_chars=max_chars)
    return out.strip()


def highlight_key_numbers_html(text: str) -> str:
    """Wrap stats in monospace for Telegram scan/share."""
    escaped = escape_telegram_html(text)

    def _repl(match: re.Match[str]) -> str:
        chunk = match.group(0)
        return f"<code>{chunk}</code>"

    return _NUMBER_HIGHLIGHT.sub(_repl, escaped)


def resolve_share_nudge(
    *,
    bucket: str,
    story_text: str,
    growth_meta: dict[str, Any] | None = None,
) -> str:
    cp = (growth_meta or {}).get("channel_product")
    if isinstance(cp, dict):
        if not cp.get("enable_share_nudge"):
            return ""
        custom = str(cp.get("share_nudge") or "").strip()
        if custom:
            return custom

    if _stable_mod(story_text, 4) != 0:
        return ""

    if bucket == "macro":
        return "Перешлите коллеге из финансов — так мы быстрее находим свою аудиторию."
    if bucket == "market":
        return "Сохраните или перешлите — полезно тем, кто следит за рынком."
    if bucket == "geo":
        return "Перешлите тем, кому актуальна геополитика."
    return "Перешлите тем, кому актуально."


def render_subscriber_wire_plain(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    why_it_matters: str | None = None,
    runtime_dir: str | None = None,
    growth_meta: dict[str, Any] | None = None,
) -> str:
    from app.editorial.public_post_formatter import format_source_footer_plain
    from app.editorial.source_attribution import apply_attribution_to_footer, resolve_source_attribution
    from publisher.public_renderer import primary_source_handle

    parts = build_subscriber_wire_parts(
        content,
        why_it_matters=why_it_matters or "",
        growth_meta=growth_meta,
    )
    out_parts: list[str] = [parts.to_plain_block()]

    chans: list[str] = []
    if isinstance(sources, list):
        chans = [str(r.get("channel") or "") for r in sources if isinstance(r, dict) and r.get("channel")]
    else:
        try:
            import json

            data = json.loads(sources or "[]")
            if isinstance(data, list):
                chans = [str(x.get("channel") or "") for x in data if isinstance(x, dict) and x.get("channel")]
        except (json.JSONDecodeError, TypeError):
            chans = []

    attr = resolve_source_attribution(chans, runtime_dir=runtime_dir)
    handle = primary_source_handle(sources)
    footer = apply_attribution_to_footer(
        format_source_footer_plain(handle) if handle else None,
        attr,
    )
    if footer:
        out_parts.append("")
        out_parts.append(footer)

    story_text = f"{parts.headline}\n{parts.body}"
    share = resolve_share_nudge(bucket=parts.bucket, story_text=story_text, growth_meta=growth_meta)
    if share:
        out_parts.append("")
        out_parts.append(share)

    return "\n".join(out_parts).strip()


def render_subscriber_wire_html(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    why_it_matters: str | None = None,
    runtime_dir: str | None = None,
    growth_meta: dict[str, Any] | None = None,
) -> str:
    from app.editorial.public_post_formatter import format_source_footer_plain
    from app.editorial.source_attribution import apply_attribution_to_footer, resolve_source_attribution
    from publisher.public_renderer import primary_source_handle

    parts = build_subscriber_wire_parts(
        content,
        why_it_matters=why_it_matters or "",
        growth_meta=growth_meta,
    )

    html_parts: list[str] = []
    if parts.headline:
        head = escape_telegram_html(parts.headline)
        if parts.breaking:
            html_parts.append(f"⚡ <b>{head}</b>")
        else:
            html_parts.append(f"<b>{head}</b>")

    if parts.body:
        paras = [p.strip() for p in parts.body.split("\n\n") if p.strip()]
        html_parts.append("\n\n".join(highlight_key_numbers_html(p) for p in paras))

    if parts.takeaway:
        html_parts.append(f"<i>→ {escape_telegram_html(parts.takeaway)}</i>")

    chans: list[str] = []
    if isinstance(sources, list):
        chans = [str(r.get("channel") or "") for r in sources if isinstance(r, dict) and r.get("channel")]
    else:
        try:
            import json

            data = json.loads(sources or "[]")
            if isinstance(data, list):
                chans = [str(x.get("channel") or "") for x in data if isinstance(x, dict) and x.get("channel")]
        except (json.JSONDecodeError, TypeError):
            chans = []

    attr = resolve_source_attribution(chans, runtime_dir=runtime_dir)
    handle = primary_source_handle(sources)
    footer = apply_attribution_to_footer(
        format_source_footer_plain(handle) if handle else None,
        attr,
    )
    if footer:
        html_parts.append(f"<i>{escape_telegram_html(footer)}</i>")

    story_text = f"{parts.headline}\n{parts.body}"
    share = resolve_share_nudge(bucket=parts.bucket, story_text=story_text, growth_meta=growth_meta)
    if share:
        html_parts.append(f"<i>{escape_telegram_html(share)}</i>")

    return sanitize_telegram_html_output("\n\n".join(p for p in html_parts if p))


def subscriber_wire_env_defaults() -> dict[str, str]:
    return {
        "NEWSROOM_PUBLISH_FORMAT": "subscriber_wire",
        "NEWSROOM_CB_BRIEF_FORMAT": "true",
        "NEWSROOM_CLEAN_CHANNEL_COPY": "true",
        "NEWSROOM_HASHTAGS_ENABLED": "false",
        "PUBLIC_WHY_IT_MATTERS": "false",
        "NEWSROOM_ENGAGEMENT_HOOK_ENABLED": "false",
        "NEWSROOM_OPEN_LOOP_ENABLED": "false",
        "NEWSROOM_BRAND_FOOTER_ENABLED": "false",
        "CHANNEL_PRODUCT_SHARE_NUDGE": "true",
        "CHANNEL_PRODUCT_OPEN_LOOP": "false",
        "GROWTH_SIGNATURE_ENABLED": "false",
    }
