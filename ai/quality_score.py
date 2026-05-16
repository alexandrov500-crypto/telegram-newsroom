from __future__ import annotations

import logging
import re
from typing import Any

from utils.structured_log import log_event

# Sensational / clickbait-ish tokens (RU + EN) — lightweight heuristics only.
_SENSATIONAL_RE = re.compile(
    r"\b("
    r"шок|сенсац|скандал|взрывной|невероятн|срочно|СРОЧНО|"
    r"никто не ожидал|все в шоке|это конец|катастроф|"
    r"shocking|unbelievable|you won'?t believe|must read|breaking\b"
    r")\b",
    re.IGNORECASE,
)
_HEDGE_RE = re.compile(
    r"\b("
    r"вероятно|возможно|по данным|по сообщениям|предварительно|"
    r"не подтвержден|неясно|по оценкам|"
    r"reportedly|allegedly|unclear|according to|may\b|might\b|could\b"
    r")\b",
    re.IGNORECASE,
)


def _bigram_repetition_ratio(text: str) -> float:
    words = re.findall(r"[\w\-]{3,}", text.lower(), flags=re.UNICODE)
    if len(words) < 6:
        return 0.0
    bigrams = [f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)]
    if not bigrams:
        return 0.0
    uniq = len(set(bigrams))
    return max(0.0, 1.0 - uniq / len(bigrams))


def _length_score(chars: int) -> float:
    if chars <= 0:
        return 0.0
    if 80 <= chars <= 950:
        return 1.0
    if chars < 80:
        return max(0.0, chars / 80.0)
    return max(0.35, 1.0 - (chars - 950) / 2000.0)


def _coherence_score(text: str) -> float:
    t = (text or "").strip()
    if len(t) < 20:
        return 0.2
    parts = re.split(r"[.!?]\s+", t)
    parts = [p for p in parts if len(p) > 10]
    if not parts:
        return 0.5
    lens = [len(p) for p in parts]
    avg = sum(lens) / len(lens)
    # Very long single "sentence" without punctuation → weaker coherence signal
    if len(parts) == 1 and avg > 400:
        return 0.45
    if 40 <= avg <= 320:
        return 1.0
    return 0.65


def _source_coverage_score(used_count: int, cluster_size: int) -> float:
    if cluster_size <= 0:
        return 1.0
    r = used_count / cluster_size
    return max(0.0, min(1.0, r))


def _factual_confidence_heuristic(text: str) -> float:
    t = text or ""
    sens = len(_SENSATIONAL_RE.findall(t))
    hed = len(_HEDGE_RE.findall(t))
    base = 0.75
    base -= min(0.45, sens * 0.12)
    base += min(0.2, hed * 0.05)
    return max(0.0, min(1.0, base))


def compute_quality_scores(
    *,
    post_text: str,
    used_ids: list[int],
    cluster_size: int,
) -> dict[str, Any]:
    t = (post_text or "").strip()
    rep = _bigram_repetition_ratio(t)
    repetition_score = max(0.0, 1.0 - 1.8 * rep)

    return {
        "coherence": round(_coherence_score(t), 3),
        "repetition": round(repetition_score, 3),
        "repetition_raw": round(rep, 4),
        "source_coverage": round(_source_coverage_score(len(used_ids), cluster_size), 3),
        "length_quality": round(_length_score(len(t)), 3),
        "factual_confidence_heuristic": round(_factual_confidence_heuristic(t), 3),
    }


def log_quality_scores(
    logger: logging.Logger,
    scores: dict[str, Any],
    *,
    enabled: bool,
) -> None:
    if not enabled:
        return
    log_event(logger, "quality.score.summary", **scores)
    if scores.get("repetition", 1.0) < 0.35:
        log_event(logger, "quality.warn.score_repetition", repetition=scores.get("repetition"))
    if scores.get("source_coverage", 1.0) < 0.25 and scores.get("source_coverage") is not None:
        log_event(logger, "quality.warn.score_low_source_coverage", source_coverage=scores.get("source_coverage"))
    if scores.get("length_quality", 1.0) < 0.4:
        log_event(logger, "quality.warn.score_length", length_quality=scores.get("length_quality"))
    if scores.get("factual_confidence_heuristic", 1.0) < 0.45:
        log_event(
            logger,
            "quality.warn.score_factual_confidence",
            factual_confidence_heuristic=scores.get("factual_confidence_heuristic"),
        )
