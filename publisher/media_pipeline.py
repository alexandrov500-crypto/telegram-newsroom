"""Autonomous draft media enrichment — never blocks terminal pipeline resolution."""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from publisher.draft_media import (
    lead_media_from_collector_cache,
    lead_media_from_raw_posts,
    media_from_extras_json,
)
from publisher.media_cache import download_image_url, validate_local_image
from publisher.media_fallback_card import render_branded_fallback_card
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

MEDIA_STATUS_PENDING = "pending"
MEDIA_STATUS_SOURCE_REUSED = "source_reused"
MEDIA_STATUS_GENERATED = "generated"
MEDIA_STATUS_FALLBACK = "fallback_generated"
MEDIA_STATUS_FAILED = "failed"
MEDIA_STATUS_SKIPPED = "skipped"

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def _media_enabled() -> bool:
    if os.getenv("MEDIA_PIPELINE_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        return False
    try:
        from app.ops.runtime_control import media_pipeline_allowed

        rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
        if not media_pipeline_allowed(rd):
            return False
    except Exception:
        pass
    return True


def _ai_image_enabled() -> bool:
    return os.getenv("MEDIA_AI_IMAGE_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def _newsroom_visual_style() -> str:
    # Unified visual language for all generated illustrations across sources.
    return (
        os.getenv(
            "MEDIA_NEWSROOM_STYLE",
            (
                "strict editorial wire-service style, deep navy and slate palette, "
                "high-contrast photojournalistic composition, subtle gradient background, "
                "single focal subject, clean geometry, no collage, no surreal elements, "
                "no text, no logos, no watermarks"
            ),
        )
        .strip()
        .replace("\n", " ")
    )


def _branded_fallback_enabled() -> bool:
    # Explicit emergency switch only; default is always-on to keep posts visual.
    force_off = os.getenv("MEDIA_FORCE_NO_FALLBACK", "").strip().lower()
    if force_off in ("1", "true", "yes", "on"):
        return False
    return True


def _cache_dir(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    return base / "media_cache" / "drafts"


def _collector_cache_root(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    return base / "media_cache"


@dataclass(frozen=True)
class MediaEnrichmentResult:
    media_status: str
    media_type: str
    media_path: str | None
    media_source_url: str | None
    media_generation_reason: str
    media_fallback_used: bool
    extras_patch: dict[str, Any]

    def tick_detail_fields(self) -> dict[str, Any]:
        return {
            "media_status": self.media_status,
            "media_type": self.media_type,
            "media_source": self.media_source_url or "",
            "media_fallback": self.media_fallback_used,
        }


def _build_media_extra(
    *,
    local_path: str,
    media_type: str,
    media_status: str,
    media_source_url: str | None,
    media_generation_reason: str,
    media_fallback_used: bool,
    message_id: int | None = None,
    chat_id: int | None = None,
    width: int | None = None,
    height: int | None = None,
    duration: int | None = None,
) -> dict[str, Any]:
    return {
        "media": {
            "media_type": media_type,
            "local_path": local_path,
            "media_status": media_status,
            "media_type_meta": media_type,
            "media_path": local_path,
            "media_source_url": media_source_url,
            "media_generation_reason": media_generation_reason[:240],
            "media_fallback_used": media_fallback_used,
            "message_id": message_id,
            "chat_id": chat_id,
            "width": width,
            "height": height,
            "duration": duration,
        }
    }


def _existing_local_media(payload: dict[str, Any] | None) -> MediaEnrichmentResult | None:
    if not payload:
        return None
    parsed = media_from_extras_json(json.dumps({"media": payload}))
    if not parsed:
        return None
    return MediaEnrichmentResult(
        media_status=MEDIA_STATUS_SOURCE_REUSED,
        media_type=str(parsed["media_type"]),
        media_path=str(parsed["local_path"]),
        media_source_url=str(payload.get("media_source_url") or ""),
        media_generation_reason="telethon_source",
        media_fallback_used=False,
        extras_patch=_build_media_extra(
            local_path=str(parsed["local_path"]),
            media_type=str(parsed["media_type"]),
            media_status=MEDIA_STATUS_SOURCE_REUSED,
            media_source_url=str(payload.get("media_source_url") or ""),
            media_generation_reason="telethon_source",
            media_fallback_used=False,
            message_id=payload.get("message_id"),
            chat_id=payload.get("chat_id"),
        ),
    )


def _first_url_from_posts(posts: list[Any], sources: list[dict[str, object]]) -> str | None:
    for src in sources:
        for key in ("url", "link"):
            u = str(src.get(key) or "").strip()
            if u.startswith("http"):
                return u
    for post in posts:
        text = str(getattr(post, "text", None) or "")
        m = _URL_RE.search(text)
        if m:
            return m.group(0).rstrip(".,)")
    return None


async def _try_og_image(url: str, cache_dir: Path) -> Path | None:
    try:
        from bot.editorial.media_enrichment import fetch_opengraph_media
    except ImportError:
        return None
    try:
        info = await fetch_opengraph_media(url)
    except Exception:
        return None
    if not info.has_media or not info.media_url:
        return None
    log_event(logger, "media.source_found", source="og_image", url=info.media_url[:120])
    return await download_image_url(str(info.media_url), cache_dir)


async def _try_ai_image(
    *,
    headline: str,
    category: str,
    cache_dir: Path,
    openai_client: Any,
) -> Path | None:
    if not _ai_image_enabled() or openai_client is None:
        return None
    prompt = (
        f"{_newsroom_visual_style()}. "
        f"Topic category: {category}. "
        f"Headline context: {headline[:200]}"
    )[:900]
    dest = cache_dir / f"ai_{abs(hash(prompt)) % 10**8}.jpg"
    if dest.is_file() and validate_local_image(dest):
        return dest
    try:
        resp = await openai_client.images.generate(
            model=os.getenv("MEDIA_AI_IMAGE_MODEL", "dall-e-2"),
            prompt=prompt,
            size="1024x1024",
            n=1,
        )
        url = resp.data[0].url if resp.data else None
        if not url:
            return None
        return await download_image_url(str(url), cache_dir)
    except Exception as exc:
        log_event(logger, "media.ai_generation_failed", error=repr(exc)[:200])
        return None


async def enrich_draft_media(
    *,
    runtime_dir: str | None,
    draft_body: str,
    headline: str,
    category: str,
    used_posts: list[Any],
    sources_payload: list[dict[str, object]],
    existing_media: dict[str, Any] | None = None,
    draft_id: int | None = None,
    openai_client: Any = None,
) -> MediaEnrichmentResult:
    """
    Resolve media for draft: source → OG URL → AI (optional) → branded fallback → skipped.

    Never raises; does not affect pipeline terminal_state.
    """
    log_event(logger, "media.pipeline_started", draft_id=draft_id)
    if not _media_enabled():
        res = MediaEnrichmentResult(
            media_status=MEDIA_STATUS_SKIPPED,
            media_type="none",
            media_path=None,
            media_source_url=None,
            media_generation_reason="pipeline_disabled",
            media_fallback_used=False,
            extras_patch={},
        )
        log_event(logger, "media.pipeline_completed", draft_id=draft_id, status=res.media_status)
        return res

    cache = _cache_dir(runtime_dir)
    reused = _existing_local_media(existing_media)
    if reused:
        log_event(logger, "media.pipeline_completed", draft_id=draft_id, status=reused.media_status)
        return reused

    lead = lead_media_from_raw_posts(used_posts)
    cache_hit = False
    if not lead:
        lead = lead_media_from_collector_cache(used_posts, _collector_cache_root(runtime_dir))
        cache_hit = lead is not None
    if lead and Path(str(lead["local_path"])).is_file():
        log_event(
            logger,
            "media.source_found",
            source="collector_cache" if cache_hit else "telethon",
            draft_id=draft_id,
        )
        local_path = str(lead["local_path"])
        media_type = str(lead["media_type"])
        width = lead.get("width")
        height = lead.get("height")
        duration = lead.get("duration")
        if media_type == "video":
            from publisher.video_normalize import normalize_video_for_telegram

            norm = await normalize_video_for_telegram(
                Path(local_path),
                cache,
                draft_id=draft_id,
            )
            if norm:
                local_path = str(norm.get("local_path") or local_path)
                width = norm.get("width") or width
                height = norm.get("height") or height
                duration = norm.get("duration") or duration
        res = MediaEnrichmentResult(
            media_status=MEDIA_STATUS_SOURCE_REUSED,
            media_type=media_type,
            media_path=local_path,
            media_source_url=None,
            media_generation_reason="telethon_cluster",
            media_fallback_used=False,
            extras_patch=_build_media_extra(
                local_path=local_path,
                media_type=media_type,
                media_status=MEDIA_STATUS_SOURCE_REUSED,
                media_source_url=None,
                media_generation_reason="telethon_cluster",
                media_fallback_used=False,
                message_id=lead.get("message_id"),
                chat_id=lead.get("chat_id"),
                width=int(width) if width else None,
                height=int(height) if height else None,
                duration=int(duration) if duration else None,
            ),
        )
        log_event(logger, "media.pipeline_completed", draft_id=draft_id, status=res.media_status)
        return res

    url = _first_url_from_posts(used_posts, sources_payload)
    if url:
        og_path = await _try_og_image(url, cache)
        if og_path:
            res = MediaEnrichmentResult(
                media_status=MEDIA_STATUS_SOURCE_REUSED,
                media_type="photo",
                media_path=str(og_path),
                media_source_url=url,
                media_generation_reason="og_image",
                media_fallback_used=False,
                extras_patch=_build_media_extra(
                    local_path=str(og_path),
                    media_type="photo",
                    media_status=MEDIA_STATUS_SOURCE_REUSED,
                    media_source_url=url,
                    media_generation_reason="og_image",
                    media_fallback_used=False,
                ),
            )
            log_event(logger, "media.pipeline_completed", draft_id=draft_id, status=res.media_status)
            return res

    title = (headline or draft_body.split("\n", 1)[0] if draft_body else "Newsroom")[:200]
    ai_path = await _try_ai_image(
        headline=title,
        category=category,
        cache_dir=cache,
        openai_client=openai_client,
    )
    if ai_path:
        res = MediaEnrichmentResult(
            media_status=MEDIA_STATUS_GENERATED,
            media_type="photo",
            media_path=str(ai_path),
            media_source_url=None,
            media_generation_reason="openai_image",
            media_fallback_used=False,
            extras_patch=_build_media_extra(
                local_path=str(ai_path),
                media_type="photo",
                media_status=MEDIA_STATUS_GENERATED,
                media_source_url=None,
                media_generation_reason="openai_image",
                media_fallback_used=False,
            ),
        )
        log_event(logger, "media.pipeline_completed", draft_id=draft_id, status=res.media_status)
        return res

    if not _branded_fallback_enabled():
        res = MediaEnrichmentResult(
            media_status=MEDIA_STATUS_SKIPPED,
            media_type="none",
            media_path=None,
            media_source_url=None,
            media_generation_reason="fallback_disabled",
            media_fallback_used=False,
            extras_patch={},
        )
        log_event(logger, "media.pipeline_completed", draft_id=draft_id, status=res.media_status)
        return res

    card = render_branded_fallback_card(
        headline=title,
        category=category,
        cache_dir=cache,
        draft_id=draft_id,
    )
    if card and validate_local_image(card):
        res = MediaEnrichmentResult(
            media_status=MEDIA_STATUS_FALLBACK,
            media_type="photo",
            media_path=str(card),
            media_source_url=None,
            media_generation_reason="branded_fallback_card",
            media_fallback_used=True,
            extras_patch=_build_media_extra(
                local_path=str(card),
                media_type="photo",
                media_status=MEDIA_STATUS_FALLBACK,
                media_source_url=None,
                media_generation_reason="branded_fallback_card",
                media_fallback_used=True,
            ),
        )
        log_event(logger, "media.pipeline_completed", draft_id=draft_id, status=res.media_status)
        return res

    res = MediaEnrichmentResult(
        media_status=MEDIA_STATUS_FAILED,
        media_type="none",
        media_path=None,
        media_source_url=None,
        media_generation_reason="all_tiers_failed",
        media_fallback_used=False,
        extras_patch={},
    )
    log_event(logger, "media.pipeline_failed", draft_id=draft_id, reason=res.media_generation_reason)
    log_event(logger, "media.pipeline_completed", draft_id=draft_id, status=res.media_status)
    return res


def publish_mode_for_extras(extras_json: str | None) -> str:
    media = media_from_extras_json(extras_json)
    if media and Path(media["local_path"]).is_file():
        return f"photo:{media.get('media_type', 'photo')}"
    return "text_only"
