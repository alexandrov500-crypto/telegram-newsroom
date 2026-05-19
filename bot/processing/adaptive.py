from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

SIGNAL_HOOK = "hook"
SIGNAL_HEADLINE = "headline_pattern"
SIGNAL_TOPIC = "topic"
SIGNAL_ENTITY = "entity"

_MAX_PRIORITY_BOOST = 0.08
_MAX_HEADLINE_BIAS = 0.12
_HIGH_SIGNAL_THRESHOLD = 0.62

_EMOJI_PREFIX_RE = re.compile(
    r"^([\U0001F300-\U0001FAFF\U00002600-\U000027BF]+)\s*",
    flags=re.UNICODE,
)


def headline_pattern_key(headline: str | None) -> str:
    if not headline:
        return "unknown"
    clean = re.sub(r"[^\w\s]", " ", headline.lower())
    words = [word for word in clean.split() if word][:4]
    return " ".join(words) if words else "unknown"


def language_signal_key(base_key: str, language: str | None = None) -> str:
    lang = (language or "en").strip().lower().split("-")[0] or "en"
    token = base_key.strip().lower() or "unknown"
    return f"{lang}:{token}"


def hook_signal_key(hook_line: str | None) -> str | None:
    if not hook_line or not str(hook_line).strip():
        return None
    text = str(hook_line).strip()
    match = _EMOJI_PREFIX_RE.match(text)
    if match:
        return match.group(1)
    return text[:32].lower()


def priority_boost_from_virality(topic_virality: float) -> float:
    """Bounded boost for high-performing topics."""
    if topic_virality <= 0.55:
        return 0.0
    boost = (topic_virality - 0.55) * 0.18
    return min(_MAX_PRIORITY_BOOST, max(0.0, boost))


def headline_bias_from_signals(
    hook_avg: float | None,
    pattern_avg: float | None,
) -> float:
    """Small bounded bias for headline generation feedback."""
    scores = [value for value in (hook_avg, pattern_avg) if value is not None]
    if not scores:
        return 0.0
    avg = sum(scores) / len(scores)
    if avg < _HIGH_SIGNAL_THRESHOLD:
        return 0.0
    return min(_MAX_HEADLINE_BIAS, (avg - _HIGH_SIGNAL_THRESHOLD) * 0.25)


def pick_adaptive_hook(
    rule_hook: str | None,
    hook_signals: list[tuple[str, float]],
) -> str | None:
    """Prefer historically strong hooks when signal is strong enough."""
    if hook_signals:
        best_key, best_avg = hook_signals[0]
        if best_avg >= _HIGH_SIGNAL_THRESHOLD and best_key:
            for candidate in hook_signals:
                if candidate[1] >= best_avg - 0.05:
                    logger.info(
                        "event=adaptive_signal_detected type=hook key=%r avg=%.3f",
                        candidate[0],
                        candidate[1],
                    )
                    return _hook_from_signal_key(candidate[0], rule_hook)
    return rule_hook


def _hook_from_signal_key(signal_key: str, fallback: str | None) -> str | None:
    mapping = {
        "🔥": "🔥 Major AI update",
        "⚠️": "⚠️ Regulatory update",
        "📈": "📈 Markets react",
        "🚀": "🚀 Startup news",
    }
    if signal_key in mapping:
        return mapping[signal_key]
    if fallback:
        return fallback
    return None
