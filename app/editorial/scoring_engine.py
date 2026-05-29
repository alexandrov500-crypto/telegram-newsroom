"""Deterministic editorial scoring + lane routing (breaking / normal / discard)."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass
from typing import Any

from ops.pipeline.paths import scored_items_path

_BREAKING_KW = re.compile(
    r"\b(breaking|urgent|just\s+in|экстренно|срочно|взрыв|attack|resignation|war\s+escalation)\b",
    re.I,
)

_DEFAULT_WEIGHTS: dict[str, float] = {}


@dataclass(frozen=True)
class EditorialScore:
    relevance_score: float
    impact_score: float
    urgency_score: float
    credibility_score: float
    final_priority_score: float
    lane: str  # breaking | normal | discard
    is_breaking: bool
    breaking_score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _channel_credibility(channel: str, runtime_dir: str | None) -> float:
    ch = (channel or "").strip().lower()
    from app.editorial.curated_sources import CURATED_SOURCE_CREDIBILITY, is_curated_source

    if is_curated_source(ch):
        return CURATED_SOURCE_CREDIBILITY
    default = float(_DEFAULT_WEIGHTS.get(ch, 0.55))
    try:
        from utils.source_reputation import export_channel_scores_for_priority

        scores = export_channel_scores_for_priority(runtime_dir)
        if ch in scores:
            row = scores[ch]
            computed = float(row.get("score") or 0.5)
            # Sparse reputation rows (duplicates only) must not collapse below curated default.
            pub = int(row.get("publishes") or 0)
            if pub < 3:
                return round(max(default * 0.85, computed), 4)
            return computed
    except Exception:
        pass
    return default


def _relevance_score(text: str) -> float:
    t = (text or "").lower()
    if len(t) < 20:
        return 0.1
    meme_markers = ("😂", "лол", "мем", "rofl", "haha")
    if any(m in t for m in meme_markers) and "рынок" not in t and "econom" not in t:
        return 0.15
    econ = sum(1 for w in ("рынок", "ставк", "инфляц", "fed", "ecb", "oil", "gdp", "бирж") if w in t)
    geo = sum(1 for w in ("war", "sanction", "nato", "войн", "санкц", "выбор") if w in t)
    tech = sum(1 for w in ("ai", "openai", "apple", "google", "tech", "chip") if w in t)
    signal = min(1.0, (econ + geo + tech) / 4.0)
    return round(max(0.1, 0.25 + 0.75 * signal), 4)


def _impact_score(text: str) -> float:
    t = (text or "").lower()
    high = (
        "central bank",
        "interest rate",
        "invasion",
        "explosion",
        "resign",
        "sanction",
        "default",
        "цб",
        "ключев",
        "взрыв",
        "отставк",
    )
    hits = sum(1 for w in high if w in t)
    return round(min(1.0, hits / 3.0), 4)


def _urgency_score(text: str, *, source_count: int = 1) -> float:
    t = text or ""
    kw = 0.35 if _BREAKING_KW.search(t) else 0.0
    velocity = min(0.45, 0.15 * max(0, source_count - 1))
    return round(min(1.0, kw + velocity + (0.1 if "!" in t[:80] else 0)), 4)


def score_story(
    *,
    text: str,
    sources: list[str] | None = None,
    runtime_dir: str | None = None,
    editorial_override_breaking: bool = False,
) -> EditorialScore:
    sources = list(sources or [])
    cred = 0.0
    if sources:
        cred = sum(_channel_credibility(s, runtime_dir) for s in sources) / len(sources)
    else:
        cred = 0.55

    rel = _relevance_score(text)
    imp = _impact_score(text)
    from app.editorial.source_languages import LANG_ZH, detect_text_language, language_for_channel

    if any(language_for_channel(s) == LANG_ZH for s in sources) or detect_text_language(text) == LANG_ZH:
        rel = max(rel, 0.35)
        imp = max(imp, 0.15)
        cred = max(cred, 0.72)
    urg = _urgency_score(text, source_count=len(set(sources)))
    breaking_score = round(min(1.0, 0.5 * urg + 0.3 * imp + 0.2 * cred), 4)
    is_breaking = editorial_override_breaking or (
        breaking_score >= 0.72
        or (len(set(sources)) >= 2 and urg >= 0.5)
        or bool(_BREAKING_KW.search(text or ""))
    )

    final = round(
        (0.28 * rel + 0.32 * imp + 0.22 * urg + 0.18 * cred) * 100,
        2,
    )
    if final < 40 or rel < 0.2:
        lane = "discard"
        reason = "low_relevance_or_noise"
    elif final >= 80 or is_breaking:
        lane = "breaking"
        reason = "high_priority_or_breaking_signals"
    else:
        lane = "normal"
        reason = "standard_newsroom_lane"

    return EditorialScore(
        relevance_score=rel,
        impact_score=imp,
        urgency_score=urg,
        credibility_score=round(cred, 4),
        final_priority_score=final,
        lane=lane,
        is_breaking=is_breaking,
        breaking_score=breaking_score,
        reason=reason,
    )


def persist_score(
    runtime_dir: str | None,
    *,
    article_id: str,
    score: EditorialScore,
    sources: list[str],
) -> None:
    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "article_id": article_id,
        "scores": score.to_dict(),
        "sources": sources,
    }
    path = scored_items_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
