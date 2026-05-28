"""Editorial ranking for ingest routing (Reuters-style selective amplification)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

_BREAKING_KW = re.compile(
    r"(срочно|breaking|санкци|войн|обвал|запрет|urgent|attack|war\b|explosion|"
    r"shutdown|экстренно|взрыв|default|экстренн)",
    re.I,
)
_GEO_CB = re.compile(
    r"(central\s+bank|фрс|fed\b|ecb|цб\b|минфин|минюст|geopolitic|"
    r"president|parliament|nato|регулятор)",
    re.I,
)
_MACRO = re.compile(
    r"(инфляц|gdp|cpi|ppi|росстат|macro|ставк|tariff|trade\s+war|нефт|oil\b|fx\b|"
    r"курс|бирж|exchange)",
    re.I,
)
_CRYPTO_VOL = re.compile(
    r"(bitcoin|btc\b|ethereum|крипт|crypto|defi|ликвидац|volatility|волатильн)",
    re.I,
)
_LIFESTYLE = re.compile(
    r"(мем|meme|lol|прикол|шутк|entertainment|giveaway|подписывайтесь|"
    r"to\s+the\s+moon|lifestyle)",
    re.I,
)
_COMPANY = re.compile(
    r"(earnings|ipo|merger|acquisition|отчётность|квартал|apple|google|"
    r"tesla|sber|газпром)",
    re.I,
)

_OFFICIAL_SOURCES = frozenset(
    {
        "reuters",
        "bloomberg",
        "apnews",
        "centralbank",
        "cbr",
        "minfin",
        "ministry",
    }
)
_MAJOR_MEDIA = frozenset(
    {
        "@cb_economics",
        "cb_economics",
        "@vedofon",
        "vedofon",
        "@vedomosti",
        "vedomosti",
        "@rbc_news",
        "rbc_news",
        "@decenter",
        "decenter",
    }
)


@dataclass(frozen=True)
class EditorialRankScore:
    breaking: float
    relevance: float
    credibility: float
    market_impact: float

    @property
    def final_score(self) -> float:
        return round(
            self.breaking * 0.35
            + self.relevance * 0.25
            + self.credibility * 0.20
            + self.market_impact * 0.20,
            4,
        )

    def to_dict(self) -> dict[str, float]:
        d = asdict(self)
        d["final_score"] = self.final_score
        return d


def _text(item: dict[str, Any]) -> str:
    return str(item.get("text") or item.get("content") or "")


def _source(item: dict[str, Any]) -> str:
    return str(item.get("source") or item.get("channel_name") or item.get("channel") or "").strip().lower()


def _breaking_score(text: str) -> float:
    t = text or ""
    score = 0.0
    if _BREAKING_KW.search(t):
        score = max(score, 1.0)
    if _GEO_CB.search(t):
        score = max(score, 0.8)
    if _CRYPTO_VOL.search(t):
        score = max(score, min(1.0, score + 0.3))
    if _MACRO.search(t) and _BREAKING_KW.search(t):
        score = max(score, 0.85)
    return round(min(1.0, score), 4)


def _relevance_score(text: str) -> float:
    t = text or ""
    if len(t.strip()) < 30:
        return 0.15
    if _LIFESTYLE.search(t) and not _MACRO.search(t):
        return 0.12
    hits = sum(1 for rx in (_MACRO, _GEO_CB, _COMPANY, _CRYPTO_VOL) if rx.search(t))
    return round(min(1.0, 0.25 + hits * 0.22), 4)


def _credibility_score(source: str, *, runtime_dir: str | None = None) -> float:
    s = source.lstrip("@")
    if any(off in s for off in _OFFICIAL_SOURCES):
        return 0.9
    key = source if source.startswith("@") else f"@{source}" if source else ""
    if key in _MAJOR_MEDIA or s in _MAJOR_MEDIA:
        return 0.6
    try:
        from utils.source_reputation import export_channel_scores_for_priority

        rep = export_channel_scores_for_priority(runtime_dir)
        row = rep.get(key) or rep.get(s) or {}
        if isinstance(row, dict) and row.get("score") is not None:
            return round(min(1.0, max(0.2, float(row["score"]))), 4)
    except Exception:
        pass
    return 0.3


def _market_impact_score(text: str) -> float:
    t = text or ""
    if any(
        w in t.lower()
        for w in (
            "fx",
            "oil",
            "sanction",
            "санкци",
            "central bank",
            "цб",
            "фрс",
            "trade",
            "тариф",
            "нефт",
            "курс",
        )
    ):
        return 1.0
    if _COMPANY.search(t):
        return 0.5
    if _MACRO.search(t):
        return 0.45
    return 0.1


def score_item(item: dict[str, Any], *, runtime_dir: str | None = None) -> EditorialRankScore:
    text = _text(item)
    source = _source(item)
    return EditorialRankScore(
        breaking=_breaking_score(text),
        relevance=_relevance_score(text),
        credibility=_credibility_score(source, runtime_dir=runtime_dir),
        market_impact=_market_impact_score(text),
    )
