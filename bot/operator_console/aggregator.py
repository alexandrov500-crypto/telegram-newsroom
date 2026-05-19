"""Backward-compatible re-export — prefer bot.operator_console.aggregation."""

from bot.operator_console.aggregation import (
    AggregateBuffer,
    EventAggregator,
    NotificationAggregator,
)

__all__ = ["AggregateBuffer", "EventAggregator", "NotificationAggregator"]
