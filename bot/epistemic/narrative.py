from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass

from bot.epistemic.repository import EpistemicRepository

logger = logging.getLogger(__name__)

_FRAMING_PATTERNS = (
    (re.compile(r"\burgent\b|\bbreaking\b", re.I), "urgency"),
    (re.compile(r"\bblame\b|\bfault\b", re.I), "attribution"),
    (re.compile(r"\bexclusive\b|\brevealed\b", re.I), "sensational"),
    (re.compile(r"\bceasefire\b|\bescalat", re.I), "conflict"),
)


@dataclass(frozen=True)
class NarrativeFingerprint:
    narrative_id: str
    fingerprint: str
    framing_tags: tuple[str, ...]
    anomaly_score: float


class NarrativeTracker:
    """Narrative evolution, framing shifts, and propagation anomalies."""

    def __init__(self, repository: EpistemicRepository) -> None:
        self._repo = repository

    @staticmethod
    def fingerprint_text(title: str, summary: str | None = None) -> str:
        text = f"{title} {summary or ''}".lower()[:300]
        return hashlib.sha256(text.encode()).hexdigest()[:20]

    def analyze_framing(self, title: str, summary: str | None = None) -> list[str]:
        text = f"{title} {summary or ''}"
        return [tag for pattern, tag in _FRAMING_PATTERNS if pattern.search(text)]

    def track(
        self,
        *,
        topic: str,
        title: str,
        summary: str | None = None,
        region: str | None = None,
        source_count: int = 1,
    ) -> NarrativeFingerprint:
        fp = self.fingerprint_text(title, summary)
        narrative_id = f"narr:{hashlib.sha256(topic.encode()).hexdigest()[:12]}"
        framing_tags = self.analyze_framing(title, summary)
        anomaly = 0.0
        if source_count < 2:
            anomaly += 0.2
        if "sensational" in framing_tags and source_count < 3:
            anomaly += 0.3

        existing = self._repo.latest_snapshot(f"narrative:{narrative_id}")
        if existing and existing.get("fingerprint") != fp:
            anomaly += 0.25
            self._repo.append_narrative_event(
                narrative_id,
                "framing_shift",
                {"prior_fp": existing.get("fingerprint"), "new_fp": fp, "tags": framing_tags},
            )

        self._repo.upsert_narrative(
            narrative_id,
            fingerprint=fp,
            topic=topic[:200],
            framing={"tags": framing_tags, "source_count": source_count},
            region=region,
            anomaly_score=min(1.0, anomaly),
        )
        self._repo.append_narrative_event(
            narrative_id,
            "observation",
            {"title": title[:120], "region": region, "anomaly": anomaly},
        )
        return NarrativeFingerprint(
            narrative_id=narrative_id,
            fingerprint=fp,
            framing_tags=tuple(framing_tags),
            anomaly_score=anomaly,
        )

    def compare_regions(
        self,
        narrative_id: str,
        regional_fingerprints: dict[str, str],
    ) -> dict[str, object]:
        unique = set(regional_fingerprints.values())
        divergence = len(unique) > 1
        return {
            "narrative_id": narrative_id,
            "divergence": divergence,
            "regions": list(regional_fingerprints.keys()),
            "unique_fingerprints": len(unique),
            "explanation": "regional framing divergence detected" if divergence else "consistent framing",
        }
