from __future__ import annotations

from publisher.telegram_transport import (
    build_message_kwargs,
    build_photo_kwargs,
    build_video_kwargs,
    guard_media_kwargs,
    message_send_kwargs,
    photo_send_kwargs,
    video_send_kwargs,
)


def test_photo_send_kwargs_excludes_web_preview() -> None:
    kwargs = photo_send_kwargs(chat_id=-1001, caption="cap")
    assert "disable_web_page_preview" not in kwargs
    assert "link_preview_options" not in kwargs
    assert kwargs["chat_id"] == -1001
    assert kwargs["caption"] == "cap"


def test_video_send_kwargs_excludes_web_preview() -> None:
    kwargs = video_send_kwargs(chat_id=-1002, caption="vid")
    assert "disable_web_page_preview" not in kwargs
    assert "link_preview_options" not in kwargs


def test_message_send_kwargs_includes_web_preview_when_requested() -> None:
    kwargs = message_send_kwargs(chat_id=-1003, disable_web_page_preview=True)
    assert kwargs["disable_web_page_preview"] is True


def test_message_send_kwargs_can_omit_web_preview() -> None:
    kwargs = message_send_kwargs(chat_id=-1004, disable_web_page_preview=False)
    assert kwargs["disable_web_page_preview"] is False


def test_build_aliases_match_builders() -> None:
    assert build_photo_kwargs is photo_send_kwargs
    assert build_video_kwargs is video_send_kwargs
    assert build_message_kwargs is message_send_kwargs


def test_guard_media_kwargs_fail_closed_on_forbidden_keys() -> None:
    dirty = {"chat_id": -1, "caption": "x", "disable_web_page_preview": True}
    import pytest

    with pytest.raises(RuntimeError, match="Forbidden media kwargs"):
        guard_media_kwargs(dirty, transport_method="send_video", draft_id=1)


def test_send_video_no_kwargs_leak() -> None:
    """Regression: media methods must never receive disable_web_page_preview."""
    kwargs = build_video_kwargs(chat_id=-1005, caption="test")
    assert "disable_web_page_preview" not in kwargs


def test_send_photo_no_kwargs_leak() -> None:
    kwargs = build_photo_kwargs(chat_id=-1006, caption="test")
    assert "disable_web_page_preview" not in kwargs
