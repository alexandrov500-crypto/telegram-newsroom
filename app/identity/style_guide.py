"""Formal editorial style guide — tone, framing, forbidden patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Voice: analytical, implication-first, no hype
FORBIDDEN_VOICE = re.compile(
    r"(шок|сенсаци|вы\s+не\s+повер|срочно\s+смотр|100%|гарантир|"
    r"breaking\s+news\s+alert|you\s+won'?t\s+believe|must\s+see|"
    r"подписывайтесь|жми\s+лайк|click\s+here|"
    r"эксклюзивно\s+у\s+нас|только\s+у\s+нас)",
    re.I,
)

GENERIC_BOT = re.compile(
    r"(важная\s+новость|сообщается\s+что|по\s+данным\s+СМИ|"
    r"it\s+is\s+reported|sources\s+say|according\s+to\s+reports|"
    r"информационное\s+агентство|не\s+официально\s+подтверждено\s*$)",
    re.I,
)

REQUIRED_SIGNAL = re.compile(
    r"(рынк|ставк|инфляц|санкц|экспорт|импорт|капитал|волатильн|"
    r"market|rate|inflation|sanction|supply|demand|crypto|btc|eth|"
    r"геополит|энерг|нефт|газ|corporate|earnings|gdp|"
    r"влиян|последств|риск|давлен|рост|паден|impact|effect)",
    re.I,
)

FRAMING_PREFIXES: dict[str, str] = {
    "macro": "Ключевой макро-сигнал:",
    "crypto": "Крипторынок:",
    "geopolitics": "Геополитика:",
    "finance": "Рынки:",
    "energy": "Энергетика:",
    "corporate": "Corporate:",
    "general": "Сигнал:",
}

INSIGHT_CONNECTORS = (
    "Это означает для рынков:",
    "Почему это важно:",
    "Контекст:",
    "Следствие:",
)


@dataclass(frozen=True)
class StyleVerdict:
    aligned: bool
    score: float
    reason: str
    violations: tuple[str, ...]


def detect_vertical(text: str, hint: str = "") -> str:
    if hint:
        return hint.strip().lower()
    low = (text or "").lower()
    for v in ("crypto", "geopolitics", "macro", "energy", "corporate", "finance"):
        if v in low or (v == "macro" and any(x in low for x in ("fed", "ecb", "ставк", "цб"))):
            return v
    return "general"


def score_style_alignment(text: str, *, vertical: str = "general") -> StyleVerdict:
    t = (text or "").strip()
    violations: list[str] = []
    if not t or len(t) < 80:
        return StyleVerdict(False, 0.0, "too_short", ("too_short",))
    if FORBIDDEN_VOICE.search(t):
        violations.append("forbidden_voice")
    if GENERIC_BOT.search(t):
        violations.append("generic_bot_phrasing")
    score = 0.55
    if not violations:
        score += 0.15
    if REQUIRED_SIGNAL.search(t):
        score += 0.18
    sents = [s for s in re.split(r"(?<=[.!?])\s+", t) if len(s.strip()) > 20]
    if len(sents) >= 2:
        score += 0.12
    if any(p in t for p in INSIGHT_CONNECTORS):
        score += 0.1
    if re.search(r"[A-ZА-ЯЁ][a-zа-яё]+.*→|—.*[.!?]", t):
        score += 0.05
    score = round(min(1.0, score), 4)
    min_score = 0.58
    aligned = score >= min_score and not violations
    reason = "aligned" if aligned else (violations[0] if violations else "low_style_score")
    return StyleVerdict(aligned, score, reason, tuple(violations))
