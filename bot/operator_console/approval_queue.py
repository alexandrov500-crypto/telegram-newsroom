from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.operator_console.formatting import clamp_lines, escape, format_header

MAX_CARD_LINES = 15


@dataclass(order=True)
class ApprovalQueueItem:
    sort_index: float
    news_id: int
    headline: str
    summary: str
    confidence: float
    epistemic_stability: float
    contradiction_exposure: int
    misinfo_risk: float
    source_diversity: int
    replay_id: str
    cluster_id: int | None = None

    def badges(self) -> str:
        parts: list[str] = []
        if self.contradiction_exposure > 0:
            parts.append(f"⚡{self.contradiction_exposure}")
        if self.misinfo_risk >= 0.5:
            parts.append("🛡 misinfo")
        if self.confidence < 0.6:
            parts.append("? conf")
        if self.epistemic_stability < 0.65:
            parts.append("epi↓")
        return " ".join(parts) if parts else "✓"


@dataclass
class SmartApprovalQueue:
    """Priority-ordered approval batching for Telegram."""

    max_immediate: int = 3
    _items: list[ApprovalQueueItem] = field(default_factory=list)

    def enqueue(self, item: ApprovalQueueItem) -> None:
        if item.cluster_id is not None:
            for existing in self._items:
                if existing.cluster_id == item.cluster_id:
                    existing.contradiction_exposure = max(
                        existing.contradiction_exposure,
                        item.contradiction_exposure,
                    )
                    if item.sort_index < existing.sort_index:
                        existing.headline = item.headline
                        existing.summary = item.summary
                        existing.sort_index = item.sort_index
                        existing.confidence = max(existing.confidence, item.confidence)
                    return
        self._items.append(item)
        self._items.sort()

    def drain_for_digest(self, limit: int = 8) -> list[ApprovalQueueItem]:
        batch = self._items[:limit]
        self._items = self._items[limit:]
        return batch

    def pending_count(self) -> int:
        return len(self._items)

    def format_digest_message(self, items: list[ApprovalQueueItem]) -> str:
        if not items:
            return "No pending approvals."
        lines = [
            format_header("APPROVAL QUEUE", "warn"),
            f"<b>{len(items)}</b> stories (batch) · highest priority first",
            "",
        ]
        for it in items:
            badges = it.badges()
            lines.append(
                f"• <code>#{it.news_id}</code> pri={it.sort_index:.2f} {badges}\n"
                f"  {escape(it.headline[:100])}\n"
                f"  replay=<code>{escape(it.replay_id)}</code>"
            )
        return clamp_lines("\n".join(lines), max_lines=MAX_CARD_LINES)

    def batch_keyboard(self, items: list[ApprovalQueueItem], action: str) -> InlineKeyboardMarkup:
        ids = ",".join(str(i.news_id) for i in items[:5])
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=f"{'✅' if action == 'approve' else '❌'} Batch {action}",
                        callback_data=f"op:batch:{action}:{ids}",
                    ),
                ],
                [
                    InlineKeyboardButton(text="💡 Explain first", callback_data="op:batch:explain:" + ids),
                ],
            ]
        )

    def format_single_card(self, item: ApprovalQueueItem) -> str:
        return clamp_lines(
            "\n".join(
                [
                    format_header("APPROVAL", "warn"),
                    f"#{item.news_id} conf {item.confidence:.2f} · {item.badges()}",
                    f"epi {item.epistemic_stability:.2f} · misinfo {item.misinfo_risk:.2f} · "
                    f"src {item.source_diversity}",
                    f"replay <code>{escape(item.replay_id)}</code>",
                    f"<b>{escape(item.headline[:160])}</b>",
                    escape(item.summary[:240]),
                ]
            ),
            max_lines=MAX_CARD_LINES,
        )
