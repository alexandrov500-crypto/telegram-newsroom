"""Deterministic ingestion priority routing."""

from app.ai.routing.priority import NewsPriority, score_news

__all__ = ["NewsPriority", "score_news"]
