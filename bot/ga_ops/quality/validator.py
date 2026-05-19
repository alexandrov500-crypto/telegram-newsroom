from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bot.ga_ops.repository import GaOpsRepository

_INJECTION = re.compile(r"ignore\s+previous|system\s*:\s*you", re.I)


@dataclass(frozen=True)
class QualityVerdict:
    overall: float
    headline: float
    consistency: float
    contradiction: float
    toxicity: float
    readability: float
    passed: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, float | bool | list[str]]:
        return {
            "overall": self.overall,
            "headline": self.headline,
            "consistency": self.consistency,
            "contradiction": self.contradiction,
            "toxicity": self.toxicity,
            "readability": self.readability,
            "passed": self.passed,
            "blockers": list(self.blockers),
        }


@dataclass
class AiQualityValidator:
    """Runtime AI output quality checks before publish."""

    repository: GaOpsRepository
    min_overall: float = 0.65

    def evaluate(
        self,
        *,
        headline: str,
        summary: str,
        story_id: int | None = None,
        pending_news_id: int | None = None,
        translations: dict[str, str] | None = None,
        contradiction_score: float = 0.0,
    ) -> QualityVerdict:
        blockers: list[str] = []
        h = headline.strip()
        headline_score = 0.9
        if len(h) < 12:
            headline_score = 0.4
            blockers.append("headline_too_short")
        if len(h) > 200:
            headline_score = 0.5
            blockers.append("headline_too_long")

        toxicity = 0.0
        if _INJECTION.search(h + " " + summary):
            toxicity = 0.9
            blockers.append("injection_pattern")

        words = summary.split()
        readability = min(1.0, len(words) / 40.0) if words else 0.3
        if len(words) < 15:
            blockers.append("summary_thin")

        consistency = 1.0
        if translations and len(translations) >= 2:
            keys = list(translations.keys())
            a = set(translations[keys[0]].lower().split()[:30])
            b = set(translations[keys[1]].lower().split()[:30])
            overlap = len(a & b) / max(len(a | b), 1)
            consistency = overlap

        hallucination_drift = 0.0
        if story_id is not None:
            prev = self.repository.quality_for_story(story_id)
            if prev and abs(float(prev["overall_score"]) - headline_score) > 0.4:
                hallucination_drift = 0.3

        contradiction = min(1.0, contradiction_score + hallucination_drift)
        overall = (
            headline_score * 0.25
            + consistency * 0.2
            + (1.0 - contradiction) * 0.2
            + (1.0 - toxicity) * 0.15
            + readability * 0.2
        )
        passed = overall >= self.min_overall and not blockers
        verdict = QualityVerdict(
            overall=overall,
            headline=headline_score,
            consistency=consistency,
            contradiction=contradiction,
            toxicity=toxicity,
            readability=readability,
            passed=passed,
            blockers=tuple(blockers),
        )
        self.repository.record_quality(
            story_id=story_id,
            pending_news_id=pending_news_id,
            scores={
                "headline": headline_score,
                "consistency": consistency,
                "contradiction": contradiction,
                "toxicity": toxicity,
                "readability": readability,
            },
            overall=overall,
        )
        return verdict

    def trend_avg(self) -> float:
        scores = self.repository.quality_trend(limit=24)
        return sum(scores) / len(scores) if scores else 0.0

    def trace_text(self, story_id: int) -> str:
        row = self.repository.quality_for_story(story_id)
        if not row:
            return f"No quality trace for story #{story_id}"
        lines = [
            f"<b>Quality trace</b> #{story_id}",
            f"Overall {row['overall_score']:.2f}",
            f"Headline {row.get('headline_score', 0):.2f} · "
            f"Read {row.get('readability_score', 0):.2f}",
        ]
        return "\n".join(lines)
