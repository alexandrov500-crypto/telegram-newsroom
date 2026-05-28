"""Deterministic branded fallback illustration (local, no network)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

# Telegram-friendly 4:3
_CARD_W = 1280
_CARD_H = 960


def render_branded_fallback_card(
    *,
    headline: str,
    category: str = "news",
    cache_dir: Path,
    draft_id: int | None = None,
) -> Path | None:
    """Render PNG/JPEG card; never raises."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{draft_id}" if draft_id else ""
    dest = cache_dir / f"fallback_card{suffix}.jpg"
    title = (headline or "Newsroom").strip()[:120]
    cat = (category or "news").strip()[:40]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return _render_minimal_without_pillow(dest, title=title, category=cat, ts=ts)
    try:
        img = Image.new("RGB", (_CARD_W, _CARD_H), color=(18, 24, 38))
        draw = ImageDraw.Draw(img)
        for y in range(_CARD_H):
            t = y / max(_CARD_H - 1, 1)
            r = int(18 + 40 * t)
            g = int(24 + 30 * t)
            b = int(38 + 50 * t)
            draw.line([(0, y), (_CARD_W, y)], fill=(r, g, b))
        draw.rectangle([48, 48, _CARD_W - 48, _CARD_H - 48], outline=(80, 120, 200), width=4)
        font_lg = ImageFont.load_default()
        font_sm = ImageFont.load_default()
        draw.text((72, 72), "NEWSROOM", fill=(140, 180, 255), font=font_sm)
        draw.text((72, 120), cat.upper(), fill=(180, 200, 220), font=font_sm)
        _wrap_text(draw, title, xy=(72, 200), max_width=_CARD_W - 144, font=font_lg, fill=(245, 247, 250))
        draw.text((72, _CARD_H - 100), ts, fill=(160, 170, 190), font=font_sm)
        img.save(dest, format="JPEG", quality=88, optimize=True)
        if dest.stat().st_size < 512:
            return None
        log_event(logger, "media.fallback_card_rendered", path=str(dest))
        return dest
    except Exception as exc:
        log_event(logger, "media.fallback_card_failed", error=repr(exc)[:160])
        return _render_minimal_without_pillow(dest, title=title, category=cat, ts=ts)


def _wrap_text(draw, text: str, *, xy: tuple[int, int], max_width: int, font, fill) -> None:
    words = text.split()
    lines: list[str] = []
    line = ""
    for w in words:
        trial = f"{line} {w}".strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = w
    if line:
        lines.append(line)
    x, y = xy
    for ln in lines[:8]:
        draw.text((x, y), ln, fill=fill, font=font)
        y += 28


def _render_minimal_without_pillow(
    dest: Path,
    *,
    title: str,
    category: str,
    ts: str,
) -> Path | None:
    """Tiny valid JPEG placeholder when Pillow is unavailable."""
    try:
        from PIL import Image  # noqa: F401 — only if somehow partial install
    except ImportError:
        pass
    # Minimal JFIF SOI + EOI (dark 1x1 expanded by Telegram is OK for fallback signal)
    minimal_jpeg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' \",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&\'()*456789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd0\x7f\xff\xd9"
    )
    dest.write_bytes(minimal_jpeg)
    meta = dest.with_suffix(".txt")
    meta.write_text(f"{title}\n{category}\n{ts}\n", encoding="utf-8")
    return dest if dest.stat().st_size >= 100 else None
