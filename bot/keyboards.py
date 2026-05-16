from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.models import DraftStatus


def draft_actions_keyboard(draft_id: int, *, status: str | None = None) -> InlineKeyboardMarkup:
    st = (status or "").lower()
    row1 = [
        InlineKeyboardButton(text="✅ Publish", callback_data=f"pub:{draft_id}"),
        InlineKeyboardButton(text="⛔ Reject", callback_data=f"rej:{draft_id}"),
    ]
    row2 = [
        InlineKeyboardButton(text="📅 Schedule", callback_data=f"schtip:{draft_id}"),
        InlineKeyboardButton(text="👁 Preview", callback_data=f"pre:{draft_id}"),
    ]
    row3 = [
        InlineKeyboardButton(text="💡 Explain", callback_data=f"exp:{draft_id}"),
        InlineKeyboardButton(text="📑 Diff", callback_data=f"diff:{draft_id}"),
    ]
    row4 = [InlineKeyboardButton(text="✨ Suggest title", callback_data=f"rett:{draft_id}")]
    rows = [row1, row2, row3, row4]
    if st == DraftStatus.FAILED.value:
        rows.append([InlineKeyboardButton(text="🔁 Retry publish", callback_data=f"retry:{draft_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def queue_pagination_keyboard(*, page: int, has_next: bool, mode: str = "fifo") -> InlineKeyboardMarkup:
    mode_key = mode if mode in ("fifo", "priority", "breaking") else "fifo"
    prev_p = max(0, page - 1)
    buttons: list[InlineKeyboardButton] = []
    if page > 0:
        buttons.append(InlineKeyboardButton(text="⬅️ Prev", callback_data=f"qpage:{prev_p}:{mode_key}"))
    if has_next:
        buttons.append(InlineKeyboardButton(text="Next ➡️", callback_data=f"qpage:{page + 1}:{mode_key}"))
    if not buttons:
        return InlineKeyboardMarkup(inline_keyboard=[])
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
