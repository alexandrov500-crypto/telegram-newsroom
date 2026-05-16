from __future__ import annotations

from bot import handlers
from bot.keyboards import draft_actions_keyboard, queue_pagination_keyboard


def test_queue_page_parse() -> None:
    assert handlers._queue_page_zero_based("/queue") == 0
    assert handlers._queue_page_zero_based("/queue 2") == 1


def test_queue_keyboard_next_only() -> None:
    kb = queue_pagination_keyboard(page=0, has_next=True, mode="fifo")
    assert len(kb.inline_keyboard[0]) >= 1


def test_draft_keyboard_has_schedule_preview() -> None:
    kb = draft_actions_keyboard(7, status="pending")
    data = " ".join(b.callback_data for row in kb.inline_keyboard for b in row)
    assert "schtip:7" in data
    assert "pre:7" in data
    assert "rett:7" in data


def test_parse_edit_title() -> None:
    pr = handlers._parse_id_and_rest("edit_title", "/edit_title 9 Hello world")
    assert pr == (9, "Hello world")
