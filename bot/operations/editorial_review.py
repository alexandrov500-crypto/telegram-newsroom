from __future__ import annotations

from dataclasses import dataclass

from bot.operations.repository import OperationsRepository


@dataclass(frozen=True)
class ReviewPanel:
    review_type: str
    target_id: str
    prompt: str


REVIEW_PANELS = (
    ReviewPanel("digest_quality", "digest", "Rate digest usefulness 0-1"),
    ReviewPanel("confidence_explainability", "epistemic", "Was confidence explanation useful?"),
    ReviewPanel("misinformation_accuracy", "alert", "Was misinformation flag accurate?"),
    ReviewPanel("contradiction_usefulness", "contradiction", "Was contradiction signal useful?"),
    ReviewPanel("routing_decision", "route", "Was model routing appropriate?"),
)


class EditorialValidationWorkflow:
    """Human editorial evaluation and feedback aggregation."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    def submit_review(
        self,
        review_type: str,
        target_id: str,
        *,
        score: float | None = None,
        useful: bool | None = None,
        annotation: str | None = None,
        operator_id: str | None = None,
    ) -> int:
        return self._repo.record_editorial_review(
            review_type,
            target_id,
            score=score,
            useful=useful,
            annotation=annotation,
            operator_id=operator_id,
        )

    def aggregate_feedback(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for panel in REVIEW_PANELS:
            out[panel.review_type] = self._repo.editorial_review_stats(panel.review_type)
        return out

    def usefulness_report(self) -> str:
        agg = self.aggregate_feedback()
        lines = ["Editorial validation summary:"]
        for kind, stats in agg.items():
            if stats["count"] == 0:
                continue
            lines.append(
                f"- {kind}: n={stats['count']} avg_score={stats['avg_score']:.2f} "
                f"useful_rate={stats['avg_useful']:.2f}"
            )
        return "\n".join(lines) if len(lines) > 1 else "No editorial reviews yet."
