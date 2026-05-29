"""Normalize source videos for Telegram channel feed (16:9 letterbox, SAR=1)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_DEFAULT_W = 1280
_DEFAULT_H = 720


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _target_size() -> tuple[int, int]:
    try:
        w = int(os.getenv("TELEGRAM_VIDEO_WIDTH", str(_DEFAULT_W)))
        h = int(os.getenv("TELEGRAM_VIDEO_HEIGHT", str(_DEFAULT_H)))
        return max(640, w), max(360, h)
    except ValueError:
        return _DEFAULT_W, _DEFAULT_H


def _probe_video(path: Path) -> dict[str, int | float | None]:
    if not _ffmpeg_available() or not path.is_file():
        return {}
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,duration",
        "-of",
        "json",
        str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False)
        if out.returncode != 0:
            return {}
        data = json.loads(out.stdout or "{}")
        streams = data.get("streams") or []
        if not streams:
            return {}
        st = streams[0]
        width = int(st.get("width") or 0) or None
        height = int(st.get("height") or 0) or None
        duration_raw = st.get("duration")
        duration = int(float(duration_raw)) if duration_raw else None
        return {"width": width, "height": height, "duration": duration}
    except Exception as exc:
        log_event(logger, "media.video_probe_failed", path=str(path), error=repr(exc)[:160])
        return {}


def _normalize_sync(source: Path, dest: Path, *, target_w: int, target_h: int) -> dict[str, int | float | None]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    vf = (
        f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
        f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        os.getenv("TELEGRAM_VIDEO_FFMPEG_PRESET", "veryfast"),
        "-crf",
        os.getenv("TELEGRAM_VIDEO_CRF", "23"),
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-an",
        str(dest),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=120, check=False)
        if proc.returncode != 0 or not dest.is_file() or dest.stat().st_size < 4096:
            log_event(
                logger,
                "media.video_normalize_failed",
                source=str(source),
                stderr=(proc.stderr or b"").decode(errors="replace")[:240],
            )
            return {}
        meta = _probe_video(dest)
        meta.setdefault("width", target_w)
        meta.setdefault("height", target_h)
        meta["local_path"] = str(dest.resolve())
        return meta
    except Exception as exc:
        log_event(logger, "media.video_normalize_failed", source=str(source), error=repr(exc)[:200])
        return {}


async def normalize_video_for_telegram(
    source_path: Path,
    cache_dir: Path,
    *,
    draft_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Letterbox/pad video to Telegram-friendly 16:9. Returns media fields or None to keep original.
    """
    if os.getenv("TELEGRAM_VIDEO_NORMALIZE_ENABLED", "true").strip().lower() in ("0", "false", "no"):
        meta = _probe_video(source_path)
        if not meta:
            return None
        meta["local_path"] = str(source_path.resolve())
        return meta

    if not _ffmpeg_available():
        meta = _probe_video(source_path)
        if meta:
            meta["local_path"] = str(source_path.resolve())
            return meta
        return None

    target_w, target_h = _target_size()
    suffix = f"_{draft_id}" if draft_id is not None else ""
    dest = cache_dir / f"tg_norm{suffix}.mp4"
    if dest.is_file() and dest.stat().st_size > 4096:
        meta = _probe_video(dest)
        meta["local_path"] = str(dest.resolve())
        return meta

    meta = await asyncio.to_thread(_normalize_sync, source_path, dest, target_w=target_w, target_h=target_h)
    if not meta:
        fallback = _probe_video(source_path)
        if fallback:
            fallback["local_path"] = str(source_path.resolve())
            return fallback
        return None
    log_event(
        logger,
        "media.video_normalized",
        draft_id=draft_id,
        path=str(dest),
        width=meta.get("width"),
        height=meta.get("height"),
    )
    return meta
