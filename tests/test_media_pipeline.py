"""Media enrichment pipeline — non-blocking, deterministic fallbacks."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from publisher.draft_media import media_from_extras_json
from publisher.media_cache import validate_local_image
from publisher.media_fallback_card import render_branded_fallback_card
from publisher.media_pipeline import (
    MEDIA_STATUS_FAILED,
    MEDIA_STATUS_FALLBACK,
    MEDIA_STATUS_SKIPPED,
    MEDIA_STATUS_SOURCE_REUSED,
    enrich_draft_media,
    publish_mode_for_extras,
)


class _Post:
    def __init__(self, extras: str = "{}", text: str = "") -> None:
        self.extras = extras
        self.text = text


def test_enrich_skipped_when_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEDIA_PIPELINE_ENABLED", "false")
    res = asyncio.run(
        enrich_draft_media(
        runtime_dir=str(tmp_path),
        draft_body="Hello",
        headline="Title",
        category="news",
        used_posts=[],
        sources_payload=[],
        )
    )
    assert res.media_status == MEDIA_STATUS_SKIPPED


def test_validate_rejects_tiny_file(tmp_path: Path) -> None:
    p = tmp_path / "tiny.jpg"
    p.write_bytes(b"\xff\xd8\xff" + b"x" * 10)
    assert validate_local_image(p) is False


def test_fallback_card_renders(tmp_path: Path) -> None:
    out = render_branded_fallback_card(
        headline="Test headline for card",
        category="markets",
        cache_dir=tmp_path / "cards",
        draft_id=99,
    )
    assert out is not None
    assert out.is_file()
    assert out.stat().st_size >= 100


def test_enrich_source_from_telethon(tmp_path: Path) -> None:
    img = tmp_path / "src.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 600)
    posts = [
        _Post(
            json.dumps(
                {
                    "media": {
                        "media_type": "photo",
                        "local_path": str(img),
                        "message_id": 1,
                    }
                }
            )
        )
    ]
    res = asyncio.run(
        enrich_draft_media(
            runtime_dir=str(tmp_path),
            draft_body="body",
            headline="H",
            category="news",
            used_posts=posts,
            sources_payload=[],
        )
    )
    assert res.media_status == MEDIA_STATUS_SOURCE_REUSED
    assert res.media_path == str(img)


def test_enrich_fallback_when_no_source(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEDIA_AI_IMAGE_ENABLED", "false")
    res = asyncio.run(
        enrich_draft_media(
        runtime_dir=str(tmp_path),
        draft_body="Only text",
        headline="Fallback headline",
        category="news",
        used_posts=[],
        sources_payload=[],
        )
    )
    assert res.media_status in (MEDIA_STATUS_FALLBACK, MEDIA_STATUS_FAILED)
    if res.media_status == MEDIA_STATUS_FALLBACK:
        assert res.media_fallback_used is True
        assert res.extras_patch


def test_publish_mode_text_only() -> None:
    assert publish_mode_for_extras("{}") == "text_only"


def test_publish_mode_photo(tmp_path: Path) -> None:
    img = tmp_path / "p.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 600)
    extras = json.dumps({"media": {"media_type": "photo", "local_path": str(img)}})
    assert publish_mode_for_extras(extras).startswith("photo:")


def test_media_from_extras_extended_fields(tmp_path: Path) -> None:
    img = tmp_path / "x.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 600)
    payload = json.dumps(
        {
            "media": {
                "media_type": "photo",
                "local_path": str(img),
                "media_status": "fallback_generated",
                "media_fallback_used": True,
            }
        }
    )
    m = media_from_extras_json(payload)
    assert m is not None
