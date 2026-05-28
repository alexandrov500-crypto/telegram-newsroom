"""Russian labels for operator-facing draft moderation UI (Telegram bot)."""

from __future__ import annotations

DRAFT_STATUS_RU: dict[str, str] = {
    "pending": "ожидает",
    "approved": "одобрен",
    "publishing": "публикуется",
    "published": "опубликован",
    "rejected": "отклонён",
    "failed": "ошибка",
}

DUPLICATE_SEVERITY_RU: dict[str, str] = {
    "none": "нет",
    "low": "низкая",
    "medium": "средняя",
    "high": "высокая",
}

PRIORITY_LEVEL_RU: dict[str, str] = {
    "HIGH": "высокий",
    "MEDIUM": "средний",
    "LOW": "низкий",
    "CRITICAL": "критический",
}

LEVEL_RU: dict[str, str] = {
    "high": "высокий",
    "medium": "средний",
    "low": "низкий",
}

QUALITY_METRIC_RU: dict[str, str] = {
    "coherence": "связность",
    "factual_confidence_heuristic": "достоверность (эвристика)",
    "length_quality": "длина текста",
    "repetition": "повторы",
    "source_coverage": "покрытие источников",
    "uniqueness": "уникальность",
    "readability": "читаемость",
}

REASONING_KEY_RU: dict[str, str] = {
    "urgency": "срочность",
    "novelty": "новизна",
    "diversity": "разнообразие",
    "dup_signal": "сигнал дубликата",
    "coherence": "связность",
    "conf": "достоверность",
    "rep": "репутация",
    "relevance_total": "релевантность",
    "duplicate_suppression": "подавление дубликатов",
}

# Stable scoring / pipeline reason codes → Russian (operator panel).
REASON_CODE_RU: dict[str, str] = {
    # editorial.scoring.explainability.REASON_CATALOG
    "multi_source_confirmation": "подтверждение несколькими источниками",
    "high_semantic_novelty": "высокая семантическая новизна",
    "low_novelty_vs_recent": "низкая новизна относительно недавних черновиков",
    "trusted_source": "доверенный источник",
    "low_source_trust": "смешанное или низкое доверие к источникам",
    "large_active_cluster": "крупный активный кластер",
    "moderate_cluster_depth": "умеренная глубина кластера",
    "duplicate_risk_elevated": "повышенный риск дубликата",
    "low_duplicate_overlap": "низкое пересечение с дубликатами",
    "cross_source_convergence": "сходимость нескольких источников",
    "strong_language_quality": "сильные языковые эвристики",
    "weak_language_quality": "слабые языковые эвристики",
    "publication_priority_elevated": "повышенный приоритет публикации",
    "editorial_priority_escalation": "эскалация редакционного приоритета",
    # English labels stored in DB (legacy drafts)
    "multi-source confirmation": "подтверждение несколькими источниками",
    "high semantic novelty": "высокая семантическая новизна",
    "low novelty vs recent drafts": "низкая новизна относительно недавних черновиков",
    "trusted source": "доверенный источник",
    "mixed or low source trust": "смешанное или низкое доверие к источникам",
    "large active cluster": "крупный активный кластер",
    "moderate cluster depth": "умеренная глубина кластера",
    "duplicate risk elevated": "повышенный риск дубликата",
    "low duplicate overlap": "низкое пересечение с дубликатами",
    "cross-source convergence": "сходимость нескольких источников",
    "strong language quality heuristics": "сильные языковые эвристики",
    "weak language quality heuristics": "слабые языковые эвристики",
    "publication priority elevated": "повышенный приоритет публикации",
    "editorial priority escalation": "эскалация редакционного приоритета",
    # governance.ranking
    "high_freshness": "высокая свежесть",
    "trusted_sources": "доверенные источники",
    "operator_override": "ручное переопределение оператора",
    # pipeline_decision
    "suppression_ttl_active": "активно подавление (TTL)",
    "duplicate_storm_suppress": "шторм дубликатов — подавление",
    "saturated_topic_and_high_duplicate_signal": "перегретая тема и сильный сигнал дубликата",
    "cooldown_update_low_relevance": "обновление в cooldown при низкой релевантности",
    "very_low_relevance_non_new": "очень низкая релевантность (не новое событие)",
    "policy_hold_for_review_duplicate_signal": "удержание на проверку: сигнал дубликата",
    "urgency_with_saturation": "срочность при перегретой теме",
    # cadence
    "cadence_recent_publish_gap_short": "короткий интервал после последней публикации",
    "cadence_repeated_topic_recent": "та же тема недавно публиковалась",
    "cadence_quiet_hours": "тихие часы (cadence)",
    # diversity_controls
    "topic_cooldown": "cooldown по теме",
    "topic_on_cooldown": "тема на cooldown",
    "source_cooldown": "cooldown по источнику",
    "source_on_cooldown": "источник на cooldown",
    # relevance / events
    "topic_memory_hit": "совпадение с памятью тем",
    "event_new": "новое событие",
    "event_update": "обновление события",
    "duplicate_high": "высокий дубликат",
    "policy_low_source_diversity": "политика: мало разнообразия источников",
    "policy_stale_topic_penalty": "политика: штраф за устаревшую тему",
    "policy_oversaturated_topic_penalty": "политика: перегретая тема",
    "policy_evergreen_update_penalty": "политика: штраф за evergreen-обновление",
    "exact_fingerprint_match": "точное совпадение отпечатка",
    "high_lexical_overlap_with_recent": "высокое лексическое пересечение с недавними",
    "partial_overlap": "частичное пересечение",
    "no_strong_match": "нет сильного совпадения",
    # misc UI
    "high_priority_score": "высокий приоритетный балл",
    "Check overlap": "проверьте пересечение",
    "Long post": "длинный пост",
    "Review soon.": "скорее на проверку",
    "matched keywords": "совпадение по ключевым словам",
    "urgency_keywords": "ключевые слова срочности",
}

MODERATION_HINT_RU: dict[str, str] = {
    "Normal queue priority.": "Обычный приоритет в очереди.",
}

REWRITE_MODE_RU: dict[str, str] = {
    "short": "короткий",
    "formal": "формальный",
    "urgent": "срочный",
    "neutral": "нейтральный",
}

_PUBLISH_PRIORITY_RU = {
    "HIGH": "ВЫСОКИЙ",
    "MEDIUM": "СРЕДНИЙ",
    "LOW": "НИЗКИЙ",
    "URGENT": "СРОЧНЫЙ",
    "CRITICAL": "КРИТИЧЕСКИЙ",
}


def tr_draft_status(status: str) -> str:
    key = (status or "").strip().lower()
    return DRAFT_STATUS_RU.get(key, status or "—")


def tr_duplicate_severity(severity: str) -> str:
    key = (severity or "none").strip().lower()
    return DUPLICATE_SEVERITY_RU.get(key, severity or "—")


def tr_priority_level(level: str) -> str:
    key = (level or "").strip().upper()
    return PRIORITY_LEVEL_RU.get(key, (level or "—").lower())


def tr_level_label(level: str) -> str:
    key = (level or "").strip().lower()
    return LEVEL_RU.get(key, level or "—")


def tr_publish_priority_label(label: str) -> str:
    key = (label or "").strip().upper()
    return _PUBLISH_PRIORITY_RU.get(key, label or "—")


def tr_quality_metric(key: str) -> str:
    k = (key or "").strip()
    return QUALITY_METRIC_RU.get(k, k.replace("_", " "))


def tr_moderation_hint(hint: str) -> str:
    h = (hint or "").strip()
    return MODERATION_HINT_RU.get(h, h)


def tr_yes_no(flag: bool) -> str:
    return "да" if flag else "нет"


def tr_scoring_reason(reason: str) -> str:
    """Translate reason code or English catalog label to Russian."""
    raw = (reason or "").strip()
    if not raw:
        return raw
    key = raw.lower().replace(" ", "_")
    if key in REASON_CODE_RU:
        return REASON_CODE_RU[key]
    if raw in REASON_CODE_RU:
        return REASON_CODE_RU[raw]
    low = raw.lower()
    if low in REASON_CODE_RU:
        return REASON_CODE_RU[low]
    return raw


def tr_reasoning_line(line: str) -> str:
    """Translate «urgency=0.40, novelty=1.00, …» style breakdowns."""
    text = (line or "").strip()
    if not text:
        return text
    parts: list[str] = []
    for seg in text.split(","):
        piece = seg.strip()
        if not piece:
            continue
        if "=" in piece:
            key, val = piece.split("=", 1)
            key = key.strip()
            label = REASONING_KEY_RU.get(key, key.replace("_", " "))
            parts.append(f"{label}={val.strip()}")
        else:
            parts.append(tr_scoring_reason(piece))
    return ", ".join(parts)


def format_source_line(channel: str, message_id: object) -> str:
    ch = str(channel or "?")
    mid = str(message_id if message_id is not None else "?")
    return f"{ch} (сообщ. {mid})"
