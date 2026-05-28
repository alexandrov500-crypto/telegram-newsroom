"""Download and validate remote images for draft media (bounded, no retries)."""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
from pathlib import Path

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_ALLOWED_IMAGE_MIMES = frozenset(
    {"image/jpeg", "image/jpg", "image/png", "image/pjpeg"}
)
_MIN_BYTES = 512
_MAX_BYTES_DEFAULT = 5_000_000


def _max_bytes() -> int:
    raw = os.getenv("MEDIA_DOWNLOAD_MAX_BYTES", str(_MAX_BYTES_DEFAULT)).strip()
    try:
        return max(_MIN_BYTES, min(int(raw), 12_000_000))
    except ValueError:
        return _MAX_BYTES_DEFAULT


def _timeout_sec() -> float:
    raw = os.getenv("MEDIA_DOWNLOAD_TIMEOUT_SEC", "8").strip()
    try:
        return max(2.0, min(float(raw), 30.0))
    except ValueError:
        return 8.0


def cache_path_for_url(cache_dir: Path, url: str, *, ext: str = ".jpg") -> Path:
    digest = hashlib.sha256(url.encode("utf-8", errors="replace")).hexdigest()[:24]
    return cache_dir / f"url_{digest}{ext}"


def validate_local_image(path: Path) -> bool:
    if not path.is_file():
        return False
    size = path.stat().st_size
    if size < _MIN_BYTES or size > _max_bytes():
        log_event(logger, "media.invalid_type", path=str(path), reason="size", size=size)
        return False
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.lower() not in _ALLOWED_IMAGE_MIMES:
        log_event(logger, "media.invalid_type", path=str(path), mime=mime)
        return False
    head = path.read_bytes()[:16]
    if head[:3] == b"\xff\xd8\xff" or head[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    log_event(logger, "media.invalid_type", path=str(path), reason="magic_bytes")
    return False


async def download_image_url(url: str, cache_dir: Path) -> Path | None:
    """Download HTTP(S) image to cache; return local path or None. Never raises."""
    if not url.startswith(("http://", "https://")):
        return None
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_path_for_url(cache_dir, url)
    if dest.is_file() and validate_local_image(dest):
        log_event(logger, "media.download_ok", url=url[:120], cached=True)
        return dest
    try:
        import httpx
    except ImportError:
        return None
    timeout = _timeout_sec()
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(3.0, timeout)),
            follow_redirects=True,
            headers={"User-Agent": "NewsroomMedia/1.0"},
        ) as client:
            resp = await client.get(url)
            if resp.status_code >= 400:
                log_event(
                    logger,
                    "media.download_failed",
                    url=url[:120],
                    status=resp.status_code,
                )
                return None
            ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
            if ctype and ctype not in _ALLOWED_IMAGE_MIMES and not ctype.startswith("image/"):
                log_event(logger, "media.invalid_type", url=url[:80], mime=ctype)
                return None
            data = resp.content
            if len(data) < _MIN_BYTES or len(data) > _max_bytes():
                log_event(logger, "media.download_failed", url=url[:80], reason="size")
                return None
            ext = ".png" if data[:8] == b"\x89PNG\r\n\x1a\n" else ".jpg"
            dest = cache_path_for_url(cache_dir, url, ext=ext)
            dest.write_bytes(data)
            if not validate_local_image(dest):
                dest.unlink(missing_ok=True)
                return None
            log_event(logger, "media.download_ok", url=url[:120], bytes=len(data))
            return dest
    except Exception as exc:
        log_event(logger, "media.download_failed", url=url[:120], error=repr(exc)[:160])
        return None
