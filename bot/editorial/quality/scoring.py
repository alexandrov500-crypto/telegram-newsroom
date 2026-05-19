from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from bot.editorial.hashtags import normalize_hashtags
from bot.editorial.quality.phrases import (
    FILLER_TOKENS,
    find_generic_openers,
    find_weak_phrases,
    tokenize,
)
from bot.editorial.quality.style_profile import DEFAULT_STYLE, NewsroomStyleProfile
from bot.editorial.source_registry import resolve_source_display


@dataclass(frozen=True, slots=True)
class EditorialDimensions:
    headline_strength: float
    summary_clarity: float
    information_density: float
    redundancy: float
    formatting_quality: float
    hashtag_quality: float
    source_attribution_quality: float
    cta_quality: float
    readability: float
    style_alignment: float


@dataclass(frozen=True, slots=True)
class EditorialQualityResult:
    editorial_quality_score: float
    dimensions: EditorialDimensions
    warnings: tuple[str, ...] = ()
    weak_phrases: tuple[str, ...] = ()
    weak_phrase_count: int = 0
    verbosity: float = 0.0
    hashtag_count: int = 0
    information_density: float = 0.0
    metadata: dict = field(default_factory=dict)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _headline_strength(headline: str, style: NewsroomStyleProfile) -> float:
    h = (headline or "").strip()
    if not h:
        return 0.0
    length = len(h)
    if length < style.min_headline_chars:
        score = 0.35
    elif length > style.max_headline_chars:
        score = 0.55
    else:
        score = 0.85
    words = tokenize(h)
    if len(words) >= 4:
        score += 0.05
    if any(ch.isdigit() for ch in h):
        score += 0.05
    weak = find_weak_phrases(h)
    score -= 0.12 * len(weak)
    if find_generic_openers(h):
        score -= 0.1
    vague = ("update", "news", "report", "development", "situation")
    if sum(1 for v in vague if v in h.lower()) >= 2:
        score -= 0.08
    return _clamp(score)


def _summary_clarity(summary: str, style: NewsroomStyleProfile) -> float:
    s = (summary or "").strip()
    if not s:
        return 0.25
    n = len(s)
    lo, hi = style.ideal_summary_chars
    if lo <= n <= hi:
        score = 0.9
    elif n < lo:
        score = 0.45
    else:
        score = max(0.4, 0.9 - (n - hi) / 800)
    sentences = [x.strip() for x in s.replace("!", ".").replace("?", ".").split(".") if x.strip()]
    if 1 <= len(sentences) <= 4:
        score += 0.05
    return _clamp(score)


def _information_density(headline: str, summary: str) -> tuple[float, float, int]:
    text = f"{headline} {summary}".strip()
    tokens = tokenize(text)
    if not tokens:
        return 0.0, 0.0, 0
    unique = set(tokens)
    filler = sum(1 for t in tokens if t in FILLER_TOKENS)
    filler_ratio = filler / len(tokens)
    unique_ratio = len(unique) / len(tokens)
    density = _clamp(unique_ratio * 1.15 - filler_ratio * 0.35)
    verbosity = _clamp(len(tokens) / 120.0)
    weak = find_weak_phrases(text)
    return density, verbosity, len(weak)


def _redundancy_score(headline: str, summary: str) -> float:
    ht, st = tokenize(headline), tokenize(summary)
    if not ht or not st:
        return 0.85
    overlap = len(set(ht) & set(st)) / max(1, len(set(ht)))
    counter = Counter(st)
    repeats = sum(1 for _, c in counter.items() if c > 2)
    penalty = min(0.35, overlap * 0.25 + repeats * 0.04)
    return _clamp(1.0 - penalty)


def _hashtag_quality(tags: list[str], style: NewsroomStyleProfile) -> tuple[float, int]:
    normalized = normalize_hashtags(tags)
    count = len(normalized)
    if count == 0:
        return 0.55, 0
    if style.min_hashtags <= count <= style.max_hashtags:
        return 0.92, count
    if count > style.max_hashtags:
        return max(0.2, 0.9 - (count - style.max_hashtags) * 0.15), count
    return 0.65, count


def _source_attribution(source: str | None) -> float:
    disp = resolve_source_display(source)
    if disp.key in ("unknown", ""):
        return 0.45
    if len(disp.name) >= 6:
        return 0.92
    return 0.7


def evaluate_editorial_quality(
    *,
    headline: str,
    summary: str,
    link: str,
    tags: list[str],
    source: str | None,
    template_key: str,
    hook_line: str | None = None,
    style: NewsroomStyleProfile | None = None,
) -> EditorialQualityResult:
    """Pure, synchronous editorial scoring. Advisory only."""
    style = style or DEFAULT_STYLE
    density, verbosity, weak_count = _information_density(headline, summary)
    weak = tuple(find_weak_phrases(f"{headline} {summary}"))
    hashtag_score, hashtag_count = _hashtag_quality(tags, style)

    dimensions = EditorialDimensions(
        headline_strength=_headline_strength(headline, style),
        summary_clarity=_summary_clarity(summary, style),
        information_density=density,
        redundancy=_redundancy_score(headline, summary),
        formatting_quality=0.88 if link.startswith("http") else 0.5,
        hashtag_quality=hashtag_score,
        source_attribution_quality=_source_attribution(source),
        cta_quality=0.9 if link.startswith("http") else 0.4,
        readability=_clamp(1.0 - verbosity * 0.35),
        style_alignment=_clamp(
            0.75
            - len(weak) * 0.06
            - (0.08 if verbosity > 0.85 else 0.0)
            + (0.05 if density >= 0.55 else 0.0),
        ),
    )

    weights = {
        "headline_strength": 0.16,
        "summary_clarity": 0.14,
        "information_density": 0.14,
        "redundancy": 0.1,
        "formatting_quality": 0.08,
        "hashtag_quality": 0.08,
        "source_attribution_quality": 0.1,
        "cta_quality": 0.06,
        "readability": 0.08,
        "style_alignment": 0.06,
    }
    overall = sum(getattr(dimensions, k) * w for k, w in weights.items())

    return EditorialQualityResult(
        editorial_quality_score=round(_clamp(overall), 3),
        dimensions=dimensions,
        weak_phrases=weak,
        weak_phrase_count=weak_count,
        verbosity=round(verbosity, 3),
        hashtag_count=hashtag_count,
        information_density=round(density, 3),
        metadata={"template_key": template_key, "hook": hook_line},
    )
