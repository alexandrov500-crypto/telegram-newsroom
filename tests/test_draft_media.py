from __future__ import annotations

import json
from pathlib import Path

from publisher.draft_media import lead_media_from_raw_posts, media_from_extras_json


class _Post:
    def __init__(self, extras: str) -> None:
        self.extras = extras


def test_media_from_extras_json(tmp_path: Path) -> None:
    img = tmp_path / "shot.jpg"
    img.write_bytes(b"x" * 600)
    payload = json.dumps(
        {"media": {"media_type": "photo", "local_path": str(img), "message_id": 1}},
    )
    media = media_from_extras_json(payload)
    assert media is not None
    assert media["media_type"] == "photo"


def test_lead_media_from_raw_posts(tmp_path: Path) -> None:
    img = tmp_path / "a.jpg"
    img.write_bytes(b"y" * 600)
    posts = [
        _Post("{}"),
        _Post(json.dumps({"media": {"media_type": "photo", "local_path": str(img)}})),
    ]
    media = lead_media_from_raw_posts(posts)
    assert media is not None
    assert media["local_path"] == str(img)
