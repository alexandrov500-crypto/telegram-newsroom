from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MEDIA_NONE = "none"
MEDIA_PHOTO = "photo"
MEDIA_VIDEO = "video"

_MIN_IMAGE_BYTES_HINT = 5_000
_MIN_DIMENSION = 200
_MAX_MEDIA_URL_LEN = 2048

_UNSUPPORTED_MIMES = frozenset(
    {
        "image/gif",
        "image/webp",
        "application/x-tgsticker",
        "video/webm",
    }
)

_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image(?::secure_url)?["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_OG_IMAGE_RE_ALT = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
    re.IGNORECASE,
)

_SKIP_URL_SUBSTRINGS = (
    "doubleclick",
    "facebook.com/tr",
    "googleads",
    "pixel.",
    "tracking",
    "analytics",
    "beacon",
    "1x1",
    "spacer.gif",
    "transparent.gif",
)

_SKIP_EXTENSIONS = (".gif", ".svg", ".ico", ".bmp")


@dataclass(frozen=True, slots=True)
class MediaInfo:
    media_type: str = MEDIA_NONE
    media_url: str | None = None
    thumbnail_url: str | None = None
    width: int | None = None
    height: int | None = None
    media_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def none(cls) -> MediaInfo:
        return cls(media_type=MEDIA_NONE)

    @property
    def has_media(self) -> bool:
        return self.media_type in (MEDIA_PHOTO, MEDIA_VIDEO) and bool(
            self.media_url or self.media_ref
        )


def _parse_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_http_url(url: str | None) -> bool:
    if not url or len(url) > _MAX_MEDIA_URL_LEN:
        return False
    parsed = urlparse(url.strip())
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _is_local_media_url(url: str | None) -> bool:
    if not url:
        return False
    return url.startswith("local://")


def _url_looks_invalid(url: str) -> bool:
    lower = url.lower()
    if any(token in lower for token in _SKIP_URL_SUBSTRINGS):
        return True
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in _SKIP_EXTENSIONS):
        return True
    if "gif" in path and "gif" in lower.split("?")[0]:
        return True
    return False


def _dimensions_too_small(width: int | None, height: int | None) -> bool:
    if width is None or height is None:
        return False
    return width < _MIN_DIMENSION or height < _MIN_DIMENSION


def _mime_to_media_type(mime: str | None) -> str | None:
    if not mime:
        return None
    mime = mime.lower().split(";")[0].strip()
    if mime in _UNSUPPORTED_MIMES:
        return None
    if mime.startswith("image/"):
        if mime == "image/gif":
            return None
        return MEDIA_PHOTO
    if mime.startswith("video/"):
        return MEDIA_VIDEO
    return None


def _is_sticker_document(document: Any) -> bool:
    attrs = getattr(document, "attributes", None) or []
    for attr in attrs:
        name = type(attr).__name__
        if name in ("DocumentAttributeSticker", "DocumentAttributeAnimated"):
            return True
    mime = getattr(document, "mime_type", None) or ""
    if "sticker" in str(mime).lower() or str(mime).lower() == "image/webp":
        return True
    return False


def validate_media(media: MediaInfo) -> MediaInfo:
    """Final gate before persistence/publish. Fail-open to none."""
    if media.media_type == MEDIA_NONE:
        return media
    if media.media_type not in (MEDIA_PHOTO, MEDIA_VIDEO):
        logger.info("event=media_invalid_skipped reason=unsupported_type type=%r", media.media_type)
        return MediaInfo.none()
    if not media.media_url and not media.media_ref:
        logger.info("event=media_invalid_skipped reason=empty_cdn_reference")
        return MediaInfo.none()
    if _dimensions_too_small(media.width, media.height):
        logger.info(
            "event=media_invalid_skipped reason=small_dimensions w=%r h=%r",
            media.width,
            media.height,
        )
        return MediaInfo.none()
    if media.media_url and not media.media_url.startswith("local://"):
        if not _is_http_url(media.media_url) or _url_looks_invalid(media.media_url):
            logger.info("event=media_invalid_skipped reason=invalid_url url=%r", (media.media_url or "")[:80])
            return MediaInfo.none()
    logger.info(
        "event=media_validated type=%s url=%r w=%r h=%r",
        media.media_type,
        (media.media_url or media.media_ref or "")[:120],
        media.width,
        media.height,
    )
    return media


def _candidate_from_url(
    url: str,
    *,
    media_type: str | None = None,
    thumbnail_url: str | None = None,
    width: int | None = None,
    height: int | None = None,
    priority: int = 0,
) -> tuple[int, MediaInfo] | None:
    url = url.strip()
    if not _is_http_url(url) or _url_looks_invalid(url):
        logger.info("event=media_invalid_skipped url=%r reason=url_filter", url[:120])
        return None
    if _dimensions_too_small(width, height):
        logger.info("event=media_invalid_skipped url=%r reason=small_dimensions", url[:120])
        return None
    resolved_type = media_type or MEDIA_PHOTO
    if resolved_type not in (MEDIA_PHOTO, MEDIA_VIDEO):
        return None
    return (
        priority,
        MediaInfo(
            media_type=resolved_type,
            media_url=url,
            thumbnail_url=thumbnail_url,
            width=width,
            height=height,
        ),
    )


def choose_best_media(*candidates: MediaInfo | None) -> MediaInfo:
    """Prefer telegram-native > enclosure > og:image > thumbnail."""
    ranked: list[tuple[int, MediaInfo]] = []
    for index, candidate in enumerate(candidates):
        if candidate is None or not candidate.has_media:
            continue
        priority = 10 - index
        if candidate.media_ref:
            priority += 50
        if candidate.media_type == MEDIA_VIDEO:
            priority += 5
        ranked.append((priority, candidate))
    if not ranked:
        return MediaInfo.none()
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    best = validate_media(ranked[0][1])
    if best.has_media:
        logger.info(
            "event=media_detected type=%s url=%r thumb=%r",
            best.media_type,
            (best.media_url or "")[:120],
            (best.thumbnail_url or "")[:80] if best.thumbnail_url else None,
        )
    return best


def extract_og_image_from_html(html: str | None) -> str | None:
    if not html:
        return None
    for pattern in (_OG_IMAGE_RE, _OG_IMAGE_RE_ALT):
        match = pattern.search(html)
        if match:
            url = match.group(1).strip()
            if _is_http_url(url) and not _url_looks_invalid(url):
                return url
    return None


def extract_rss_media(entry: Any) -> MediaInfo:
    """Extract media from a feedparser entry. Never raises."""
    candidates: list[MediaInfo | None] = []
    try:
        media_content = entry.get("media_content") or []
        if not isinstance(media_content, list):
            media_content = [media_content]
        for item in media_content:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or item.get("href")
            mime = item.get("type") or item.get("medium")
            media_type = _mime_to_media_type(str(mime) if mime else None)
            if media_type and url:
                picked = _candidate_from_url(
                    str(url),
                    media_type=media_type,
                    width=_parse_int(item.get("width")),
                    height=_parse_int(item.get("height")),
                    priority=30,
                )
                if picked:
                    candidates.append(picked[1])

        enclosures = entry.get("enclosures") or []
        if not isinstance(enclosures, list):
            enclosures = [enclosures]
        for enc in enclosures:
            if not isinstance(enc, dict):
                continue
            url = enc.get("href") or enc.get("url")
            mime = enc.get("type")
            length = _parse_int(enc.get("length"))
            media_type = _mime_to_media_type(str(mime) if mime else None)
            if url and media_type:
                if media_type == MEDIA_PHOTO and length is not None and length < _MIN_IMAGE_BYTES_HINT:
                    logger.info("event=media_invalid_skipped url=%r reason=small_file", str(url)[:80])
                    continue
                picked = _candidate_from_url(
                    str(url),
                    media_type=media_type,
                    priority=40,
                )
                if picked:
                    candidates.append(picked[1])

        thumbs = entry.get("media_thumbnail") or []
        if not isinstance(thumbs, list):
            thumbs = [thumbs]
        for thumb in thumbs:
            if not isinstance(thumb, dict):
                continue
            url = thumb.get("url")
            if url:
                picked = _candidate_from_url(
                    str(url),
                    media_type=MEDIA_PHOTO,
                    width=_parse_int(thumb.get("width")),
                    height=_parse_int(thumb.get("height")),
                    priority=10,
                )
                if picked:
                    candidates.append(picked[1])

        summary = entry.get("summary") or entry.get("description") or ""
        og = extract_og_image_from_html(str(summary))
        if og:
            picked = _candidate_from_url(og, media_type=MEDIA_PHOTO, priority=20)
            if picked:
                candidates.append(picked[1])

        links = entry.get("links") or []
        for link in links:
            if not isinstance(link, dict):
                continue
            rel = str(link.get("rel", "")).lower()
            mime = link.get("type")
            href = link.get("href")
            if href and rel in ("enclosure", "thumbnail") and mime:
                media_type = _mime_to_media_type(str(mime))
                if media_type:
                    picked = _candidate_from_url(
                        str(href),
                        media_type=media_type,
                        priority=35 if rel == "enclosure" else 12,
                    )
                    if picked:
                        candidates.append(picked[1])
    except Exception:
        logger.exception("event=media_extract_failed source=rss")
        return MediaInfo.none()

    return choose_best_media(*candidates)


def _media_from_telegram_message(message: Any) -> MediaInfo:
    if getattr(message, "photo", None):
        ref = {
            "kind": MEDIA_PHOTO,
            "message_id": int(message.id),
        }
        sizes = getattr(message.photo, "sizes", None) or []
        largest = None
        for size in sizes:
            w = getattr(size, "w", None) or getattr(size, "width", None)
            h = getattr(size, "h", None) or getattr(size, "height", None)
            if w and h:
                largest = (int(w), int(h))
        width, height = largest if largest else (None, None)
        return MediaInfo(
            media_type=MEDIA_PHOTO,
            media_url=None,
            thumbnail_url=None,
            width=width,
            height=height,
            media_ref=json.dumps(ref, separators=(",", ":")),
        )

    video = getattr(message, "video", None)
    if video is not None:
        thumb = None
        thumbs = getattr(video, "thumbs", None) or []
        if thumbs:
            thumb_obj = thumbs[-1]
            thumb_path = getattr(thumb_obj, "photo_id", None)
            if thumb_path:
                thumb = str(thumb_path)
        ref = {"kind": MEDIA_VIDEO, "message_id": int(message.id)}
        return MediaInfo(
            media_type=MEDIA_VIDEO,
            media_url=None,
            thumbnail_url=thumb,
            width=_parse_int(getattr(video, "w", None)),
            height=_parse_int(getattr(video, "h", None)),
            media_ref=json.dumps(ref, separators=(",", ":")),
        )

    document = getattr(message, "document", None)
    if document is not None:
        if _is_sticker_document(document):
            logger.info("event=media_invalid_skipped reason=sticker message_id=%s", getattr(message, "id", None))
            return MediaInfo.none()
        mime = getattr(document, "mime_type", None) or ""
        media_type = _mime_to_media_type(str(mime))
        if media_type == MEDIA_VIDEO:
            ref = {"kind": MEDIA_VIDEO, "message_id": int(message.id), "document": True}
            return MediaInfo(
                media_type=MEDIA_VIDEO,
                media_url=None,
                media_ref=json.dumps(ref, separators=(",", ":")),
            )
    return MediaInfo.none()


def extract_telegram_media(message: Any) -> MediaInfo:
    """Extract media from a Telethon message, including forwards. Never raises."""
    try:
        media = _media_from_telegram_message(message)
        if not media.has_media:
            return MediaInfo.none()
        if getattr(message, "fwd_from", None) is not None:
            ref_data = json.loads(media.media_ref or "{}")
            ref_data["forwarded"] = True
            media = MediaInfo(
                media_type=media.media_type,
                media_url=media.media_url,
                thumbnail_url=media.thumbnail_url,
                width=media.width,
                height=media.height,
                media_ref=json.dumps(ref_data, separators=(",", ":")),
            )
        return validate_media(media)
    except Exception:
        logger.exception("event=media_extract_failed source=telegram")
    return MediaInfo.none()


def select_digest_hero_media(candidates: list[MediaInfo]) -> MediaInfo:
    """Pick first valid photo (preferred) or video for digest hero."""
    for preferred in (MEDIA_PHOTO, MEDIA_VIDEO):
        for media in candidates:
            if media.media_type != preferred:
                continue
            validated = validate_media(media)
            if validated.has_media:
                return validated
    return MediaInfo.none()


async def resolve_telegram_media_url(
    client: Any,
    message: Any,
    media: MediaInfo,
    *,
    cache_dir: Any,
) -> MediaInfo:
    """
    Download Telegram-native media to a local cache path for Bot API upload.
    Fail-open: returns original media on errors.
    """
    if not media.media_ref or media.media_url:
        return media
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = await client.download_media(message, file=cache_dir / f"tg_{message.id}")
        if not path:
            return media
        local_url = f"local://{path}"
        logger.info(
            "event=media_detected type=%s local=%r",
            media.media_type,
            str(path)[:120],
        )
        resolved = MediaInfo(
            media_type=media.media_type,
            media_url=local_url,
            thumbnail_url=media.thumbnail_url,
            width=media.width,
            height=media.height,
            media_ref=media.media_ref,
        )
        return validate_media(resolved)
    except Exception:
        logger.exception("event=media_extract_failed source=telegram_download")
        return media


def merge_item_media(
    telegram_media: MediaInfo | None,
    rss_media: MediaInfo | None,
) -> MediaInfo:
    """Priority: Telegram-native > RSS enclosure > OG > thumbnail."""
    return choose_best_media(telegram_media, rss_media)
