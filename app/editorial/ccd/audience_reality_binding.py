"""Audience reality binding — write for overloaded humans, not markets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_NOISE = re.compile(
    r"(по\s+данным\s+10|пересказ|источник\s+сообщил.*источник|новости\s+ради\s+новост|"
    r"подписывайтесь|breaking\s+breaking)",
    re.I,
)
_WHY = re.compile(r"(почему\s+важ|why\s+it\s+matters|значит|implication|важно\s+в\s+одном)", re.I)
_DECISION = re.compile(r"(decision|решени|инвестор|риск|стратег|policy)", re.I)
_DUP_MACRO = re.compile(r"(инфляц.*инфляц|ставк.*ставк.*ставк)", re.I)


@dataclass(frozen=True)
class UnifiedReaderProfile:
    cognitive_load_limit: str = "medium"
    attention_span: str = "short_to_medium"
    decision_need: str = "high"
    motivation: str = "clarity_relevance_trust"
    frustration_point: str = "noise_repetition"

    def to_dict(self) -> dict[str, Any]:
        return {
            "cognitive_load_limit": self.cognitive_load_limit,
            "attention_span": self.attention_span,
            "decision_need": self.decision_need,
            "motivation": self.motivation,
            "frustration_point": self.frustration_point,
        }


@dataclass(frozen=True)
class AudienceRealityBinding:
    passes: bool
    decision_relevance: bool
    has_implication: bool
    why_one_sentence_ok: bool
    noise_detected: bool
    repetition_detected: bool
    binding_score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passes": self.passes,
            "decision_relevance": self.decision_relevance,
            "has_implication": self.has_implication,
            "why_one_sentence_ok": self.why_one_sentence_ok,
            "noise_detected": self.noise_detected,
            "repetition_detected": self.repetition_detected,
            "binding_score": round(self.binding_score, 2),
            "reason": self.reason,
            "reader_profile": UnifiedReaderProfile().to_dict(),
        }


def evaluate_audience_reality_binding(text: str) -> AudienceRealityBinding:
    t = text or ""
    noise = bool(_NOISE.search(t))
    repetition = bool(_DUP_MACRO.search(t))
    why_ok = bool(_WHY.search(t))
    decision = bool(_DECISION.search(t))

    score = 50.0
    if why_ok:
        score += 25.0
    if decision:
        score += 15.0
    if len(t.split()) >= 40:
        score += 10.0
    if noise:
        score -= 30.0
    if repetition:
        score -= 20.0
    score = max(0.0, min(100.0, score))

    passes = score >= 55 and not noise and (why_ok or decision)
    reason = "binding_ok" if passes else "fails_human_relevance"
    if noise:
        reason = "noise_forbidden"
    elif repetition:
        reason = "macro_repetition"

    return AudienceRealityBinding(
        passes=passes,
        decision_relevance=decision,
        has_implication=why_ok,
        why_one_sentence_ok=why_ok and len(t.split()) <= 280,
        noise_detected=noise,
        repetition_detected=repetition,
        binding_score=score,
        reason=reason,
    )
