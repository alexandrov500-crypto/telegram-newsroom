from __future__ import annotations

from typing import Any

from bot.live_ops.repository import LiveChannelRepository


class LiveFeedbackLoop:
    """Real audience telemetry aggregation."""

    def __init__(self, repository: LiveChannelRepository) -> None:
        self.repository = repository

    def record_publish_success(self, *, pending_news_id: int) -> None:
        self.repository.record_feedback("publish_success", 1.0, pending_news_id=pending_news_id)

    def record_publish_failure(self, *, pending_news_id: int, reason: str) -> None:
        self.repository.record_feedback(
            "publish_failure",
            1.0,
            pending_news_id=pending_news_id,
            detail={"reason": reason},
        )

    def record_operator_correction(self) -> None:
        self.repository.record_feedback("operator_correction", 1.0)

    def record_rejected_draft(self) -> None:
        self.repository.record_feedback("rejected_draft", 1.0)

    def scores(self) -> dict[str, float]:
        state = self.repository.get_state() or {}
        trust = float(state.get("trust_score", 0.85))
        stability = float(state.get("content_stability_score", 0.9))
        success_rate = self.repository.publish_success_rate()
        return {
            "trust_score": trust,
            "content_stability_score": stability,
            "publish_success_rate": success_rate,
        }

    def update_derived_scores(self) -> None:
        scores = self.scores()
        trust = scores["publish_success_rate"] * 0.5 + scores["content_stability_score"] * 0.5
        bad = self._count_ratings("bad")
        good = self._count_ratings("good")
        total = bad + good
        stability = scores["content_stability_score"]
        if total > 0:
            stability = good / total
        self.repository.update_state(
            trust_score=min(1.0, max(0.0, trust)),
            content_stability_score=min(1.0, max(0.0, stability)),
        )

    def _count_ratings(self, rating: str) -> int:
        with self.repository._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM live_channel_post_ratings WHERE rating = ?",
                (rating,),
            ).fetchone()
        return int(row[0] if row else 0)

    def feedback_html(self) -> str:
        s = self.scores()
        return (
            "<b>Live feedback</b>\n"
            f"Trust: {s['trust_score']:.0%}\n"
            f"Content stability: {s['content_stability_score']:.0%}\n"
            f"Publish success: {s['publish_success_rate']:.0%}"
        )
