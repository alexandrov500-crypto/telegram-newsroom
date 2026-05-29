"""Single public post formatter — headline, summary, why-it-matters, attribution, CTA."""

from __future__ import annotations

import json
import logging
import os
import re
from hashlib import md5
from typing import Any

from app.editorial.public_format import format_public_story
from app.editorial.growth_cadence import signature_line_for_now
from app.editorial.publish_body_scrubber import scrub_publish_plaintext
from app.editorial.source_attribution import (
    apply_attribution_to_footer,
    resolve_source_attribution,
    strip_raw_urls,
)
from app.editorial.tuning_loader import get_editorial_tuning
from app.publisher.draft_builder import polish_channel_post
from publisher.public_renderer import (
    extract_why_it_matters,
    format_why_it_matters_block,
    primary_source_handle,
    split_headline_and_body,
    strip_internal_debug_text,
)
from utils.telegram_html import escape_telegram_html, sanitize_telegram_html_output
from utils.structured_log import log_event

_CTA_LINE = "Подписывайтесь на канал — главные новости без шума."
_EMOJI_SPAM = re.compile(r"([\U0001F300-\U0001FAFF\u2600-\u27BF]){4,}")
_TABLOID = re.compile(r"(шокирующ|сенсаци|вы\s+не\s+поверите|срочно\s+узнай)", re.I)
_MACRO_RE = re.compile(
    r"(?:инфляц|(?<![а-яёa-z])ставк(?:а|и|у|е|ой|ами)(?![а-яёa-z])|"
    r"\bcpi\b|\bgdp\b|\bцб\b|\bфрс\b|\bfed\b|\becb\b|росстат|минфин)",
    re.I,
)
_CRYPTO_RE = re.compile(r"(bitcoin|btc|ethereum|eth|крипт|defi|etf)", re.I)
_GEO_RE = re.compile(r"(санкци|войн|атака|nato|parliament|президент|геополит)", re.I)
_MARKET_RE = re.compile(r"(акци|индекс|рынок|бирж|доходност|облигац|нефт|oil|fx)", re.I)

_STRIP_SOURCE_LINE = re.compile(r"^(Источник|Source|via)\s*:", re.I)
_INLINE_SOURCE = re.compile(r"(Источник|Source|via)\s*:\s*@?\w+", re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
# Word-boundary aware: avoid "ставк" inside "доставка" and "ключев.*ставк" spanning paragraphs.
_FED_RE = re.compile(
    r"(?:\bfed\b|\bfomc\b|\bфрс\b|"
    r"ключев(?:ая|ой|ую|ые)?\s+ставк(?:а|и|у|е|ой|ами)|"
    r"(?<![а-яёa-z])ставк(?:а|и|у|е|ой|ами)(?![а-яёa-z]))",
    re.I,
)
_INFLATION_RE = re.compile(r"(?:\binflation\b|\bcpi\b|\bpce\b|(?<![а-яёa-z])инфляц\w*)", re.I)
_OIL_RE = re.compile(r"(?:\boil\b|\bbrent\b|\bwti\b|(?<![а-яёa-z])нефт\w*)", re.I)
_RATES_RE = re.compile(
    r"(?:\brate(?:s)?\b|\byield(?:s)?\b|"
    r"(?<![а-яёa-z])доходност(?:ь|и|ью|ями)?|"
    r"ключев(?:ая|ой|ую|ые)?\s+ставк(?:а|и|у|е|ой|ами)?)",
    re.I,
)
_BTC_RE = re.compile(r"(bitcoin|btc|биткоин)", re.I)
_ETH_RE = re.compile(r"(ethereum|eth|эфир)", re.I)
_SP500_RE = re.compile(r"(s&p|sp500|snp500|spx)", re.I)
_NASDAQ_RE = re.compile(r"(nasdaq|ndx)", re.I)
_GOLD_RE = re.compile(r"(gold|xau|золот)", re.I)
_AI_RE = re.compile(
    r"(\bai\b|(?:^|[\s,.:;«»])ии(?:[\s,.:;»]|$)|искусственн\w*\s+интеллект)",
    re.I,
)
_NVIDIA_RE = re.compile(r"(nvidia|nvda)", re.I)
_OPENAI_RE = re.compile(r"(openai|chatgpt|gpt-)", re.I)
_SEMIS_RE = re.compile(r"(semiconductor|chip|полупровод)", re.I)
_CHINA_RE = re.compile(r"(china|китай|beijing|пекин)", re.I)
_USA_RE = re.compile(r"(usa|us\b|сша|washington|вашингтон)", re.I)
_RUSSIA_RE = re.compile(r"(russia|росси|москв|moscow)", re.I)
_ME_RE = re.compile(r"(?:middle\s*east|ближн\w*\s+восток|(?<![a-z])\biran\b|\bisrael\b|\bgaza\b)", re.I)

logger = logging.getLogger(__name__)


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"[^\w]+", " ", (text or "").lower()).strip()


def _hook_duplicates_headline(hook: str, headline: str) -> bool:
    """A hook that merely restates the headline adds no value."""
    h = _normalize_for_compare(headline)
    k = _normalize_for_compare(re.sub(r"^[^:]+:\s*", "", hook or ""))
    if not h or not k:
        return False
    if h in k or k in h:
        return True
    hw = set(h.split())
    kw = set(k.split())
    if len(hw) < 3:
        return False
    return len(hw & kw) / len(hw) >= 0.7


def _parse_source_channels(sources: str | list[dict[str, Any]] | None) -> list[str]:
    if isinstance(sources, list):
        return [str(r.get("channel") or "") for r in sources if isinstance(r, dict) and r.get("channel")]
    try:
        data = json.loads(sources or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [str(x.get("channel") or "") for x in data if isinstance(x, dict) and x.get("channel")]


def _strip_embedded_source_lines(text: str) -> str:
    t = _INLINE_SOURCE.sub("", text or "")
    lines = []
    for ln in t.splitlines():
        if _STRIP_SOURCE_LINE.match(ln.strip()):
            continue
        lines.append(ln)
    return re.sub(r"\s{2,}", " ", "\n".join(lines)).strip()


def _dedupe_source_lines(text: str) -> str:
    lines = (text or "").splitlines()
    seen: set[str] = set()
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s.lower().startswith(("источник:", "via ", "source:")):
            key = s.lower()
            if key in seen:
                continue
            seen.add(key)
        out.append(ln)
    return "\n".join(out).strip()


def _light_tone_cleanup(text: str) -> str:
    tuning = get_editorial_tuning()
    t = _EMOJI_SPAM.sub("", text or "")
    if tuning.voice.strip_tabloid and _TABLOID.search(t):
        t = _TABLOID.sub("", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _prepare_body_plain(content: str, *, max_chars: int) -> str:
    from app.publisher.draft_builder import _repair_leading_name_glitches

    scrubbed = scrub_publish_plaintext(_repair_leading_name_glitches(content))
    cleaned = strip_internal_debug_text(scrubbed)
    return _light_tone_cleanup(polish_channel_post(cleaned, max_chars=max_chars))


def _story_bucket(text: str) -> str:
    t = (text or "").lower()
    if _CRYPTO_RE.search(t):
        return "crypto"
    if _MACRO_RE.search(t):
        return "macro"
    if _GEO_RE.search(t):
        return "geo"
    if _MARKET_RE.search(t):
        return "market"
    return "general"


def _engagement_score(text: str, bucket: str) -> float:
    base = 0.45
    ln = len((text or "").strip())
    if ln >= 220:
        base += 0.15
    elif ln >= 140:
        base += 0.08
    if bucket in {"macro", "market", "crypto", "geo"}:
        base += 0.15
    if re.search(r"\d", text or ""):
        base += 0.08
    return round(min(0.95, max(0.25, base)), 3)


def _lead_sentence(text: str, *, max_len: int = 140) -> str:
    sents = [s.strip() for s in _SENTENCE_SPLIT.split((text or "").strip()) if s.strip()]
    lead = sents[0] if sents else (text or "").strip()
    if len(lead) <= max_len:
        return lead
    cut = lead[: max_len + 1]
    sp = cut.rfind(" ")
    if sp > max_len // 2:
        return cut[:sp].rstrip()
    return lead[:max_len].rstrip()


def _engagement_hook(summary: str, bucket: str, *, headline: str = "") -> str:
    # Off by default: the hook restated the lead sentence (≈ the headline),
    # producing a redundant "Ключевой факт: <тот же заголовок>" line.
    if not _flag("NEWSROOM_ENGAGEMENT_HOOK_ENABLED", False):
        return ""
    lead = _lead_sentence(summary, max_len=130)
    if not lead:
        return ""
    lead = lead.rstrip(".!? ").strip()
    if bucket == "macro":
        hook = f"Главное для экономики: {lead}."
    elif bucket == "crypto":
        hook = f"Ключевой сигнал для крипторынка: {lead}."
    elif bucket == "geo":
        hook = f"Что важно в геоповестке: {lead}."
    elif bucket == "market":
        hook = f"Что это значит для рынка: {lead}."
    else:
        hook = f"Ключевой факт: {lead}."
    if headline and _hook_duplicates_headline(hook, headline):
        return ""
    return hook


def _adaptive_cta_line(bucket: str) -> str:
    if bucket == "macro":
        return "Подписывайтесь: ежедневно объясняем решения ЦБ, инфляцию и ставки без шума."
    if bucket == "crypto":
        return "Подписывайтесь: разбираем крипторынок и риски простым языком, без хайпа."
    if bucket == "geo":
        return "Подписывайтесь: отслеживаем геополитику и ее влияние на рынки в одном канале."
    if bucket == "market":
        return "Подписывайтесь: коротко и по делу о рынках, акциях и ключевых движениях."
    return _CTA_LINE


def _stable_mod(text: str, n: int) -> int:
    t = (text or "").encode("utf-8")
    return int(md5(t).hexdigest(), 16) % max(1, n)


def _smart_hashtags(text: str, bucket: str, *, runtime_dir: str | None = None) -> list[str]:
    if os.getenv("NEWSROOM_HASHTAGS_ENABLED", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return []
    # Country/macro tags on pure geo/diplomatic posts confuse readers — reserve for market buckets.
    if bucket not in {"macro", "market", "crypto"}:
        return []
    max_tags = 2
    try:
        max_tags = max(1, min(2, int(os.getenv("NEWSROOM_HASHTAGS_MAX", "2"))))
    except ValueError:
        max_tags = 2
    t = text or ""
    candidates: list[str] = []
    pairs = [
        ("#Fed", _FED_RE),
        ("#Inflation", _INFLATION_RE),
        ("#Oil", _OIL_RE),
        ("#Rates", _RATES_RE),
        ("#Bitcoin", _BTC_RE),
        ("#Ethereum", _ETH_RE),
        ("#SP500", _SP500_RE),
        ("#NASDAQ", _NASDAQ_RE),
        ("#Gold", _GOLD_RE),
        ("#AI", _AI_RE),
        ("#NVIDIA", _NVIDIA_RE),
        ("#OpenAI", _OPENAI_RE),
        ("#Semiconductors", _SEMIS_RE),
        ("#China", _CHINA_RE),
        ("#USA", _USA_RE),
        ("#Russia", _RUSSIA_RE),
        ("#MiddleEast", _ME_RE),
    ]
    for tag, rx in pairs:
        if rx.search(t):
            candidates.append(tag)
    # No bucket-derived fallback tags: a hashtag must reflect a term that
    # literally appears in the post, otherwise it confuses the reader.
    uniq: list[str] = []
    seen: set[str] = set()
    for tag in candidates:
        if tag in seen:
            continue
        seen.add(tag)
        uniq.append(tag)
    picked = uniq[:max_tags]
    if runtime_dir and picked:
        try:
            from app.editorial.intelligence.trend_memory import choose_hashtags, infer_narrative_cluster

            cluster_key = infer_narrative_cluster(text, category=bucket)
            picked = choose_hashtags(
                runtime_dir,
                cluster_key=cluster_key,
                candidates=picked,
                limit=max_tags,
            )
        except Exception:
            pass
    return picked


def _open_loop_line(
    bucket: str,
    engagement_score: float,
    *,
    runtime_dir: str | None = None,
    text: str = "",
) -> str:
    # Off by default: these were English templated lines that broke the
    # reading flow on a Russian channel and often had no link to the story.
    if not _flag("NEWSROOM_OPEN_LOOP_ENABLED", False):
        return ""
    if engagement_score < 0.62:
        return ""
    if runtime_dir:
        try:
            from app.editorial.intelligence.trend_memory import evaluate_narrative_strategy

            strat = evaluate_narrative_strategy(runtime_dir, text=text, category=bucket)
            if not bool(strat.get("open_loop_continuation", True)):
                return ""
            key = str(strat.get("cluster_key") or "")
            if key == "ai_boom":
                return "AI rally continues: traders now focus on capex signals and guidance."
            if key == "macro_stress":
                return "Macro stress continues: traders now focus on the next policy and inflation signals."
            if key == "geopolitical_escalation":
                return "Geopolitical pressure continues: traders now focus on energy and risk repricing."
            if key == "crypto_risk_on":
                return "Crypto risk-on continues: traders now focus on ETF flows and liquidity."
        except Exception:
            pass
    if bucket == "macro":
        return "Traders now focus on the next inflation print and policy path."
    if bucket == "crypto":
        return "Traders now focus on liquidity flows and ETF demand in the next sessions."
    if bucket == "geo":
        return "Watch closely: next geopolitical headlines can reprice risk fast."
    if bucket == "market":
        return "Traders now focus on follow-through: whether this move confirms a broader trend."
    return "Watch closely: the next sessions will define whether this narrative extends."


def _adaptive_brand_footer(text: str, engagement_score: float) -> str:
    # Off by default: English brand taglines added noise without reader value.
    if not _flag("NEWSROOM_BRAND_FOOTER_ENABLED", False):
        return ""
    if engagement_score < 0.72:
        return ""
    if _stable_mod(text, 3) != 0:
        return ""
    opts = [
        "Follow for high-signal market intelligence.",
        "Daily macro & markets briefing.",
        "Real-time financial narratives.",
    ]
    return opts[_stable_mod(text + "brand", len(opts))]


def format_public_post_plain(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    why_it_matters: str | None = None,
    include_cta: bool | None = None,
    runtime_dir: str | None = None,
    max_total_chars: int = 12000,
) -> str:
    tuning = get_editorial_tuning()
    max_body = tuning.structure.summary_max_chars
    chans = _parse_source_channels(sources)
    attr = resolve_source_attribution(chans, runtime_dir=runtime_dir)
    polished = _prepare_body_plain(content, max_chars=max_body)
    polished = _strip_embedded_source_lines(polished)
    if attr.strip_urls_from_body:
        polished = strip_raw_urls(polished)
    headline, body = split_headline_and_body(polished)
    body, embedded_why = extract_why_it_matters(body)
    why = (why_it_matters or embedded_why or "").strip()
    story = format_public_story(headline, body, why_it_matters=why)
    bucket = _story_bucket(f"{story.headline}\n{story.summary}")
    score = _engagement_score(story.summary, bucket)
    story_text = f"{story.headline}\n{story.summary}\n{story.why_it_matters}"
    tags = _smart_hashtags(story_text, bucket, runtime_dir=runtime_dir)
    open_loop = _open_loop_line(bucket, score, runtime_dir=runtime_dir, text=story_text)
    brand_footer = _adaptive_brand_footer(f"{story.headline}\n{story.summary}", score)
    parts: list[str] = []
    signature = signature_line_for_now()
    if signature:
        parts.append(signature)
        parts.append("")
    if story.headline:
        parts.append(story.headline)
    if story.summary:
        hook = _engagement_hook(story.summary, bucket, headline=story.headline)
        if hook:
            parts.append(hook)
            parts.append("")
        parts.append(story.summary)
    if story.why_it_matters:
        parts.append("")
        parts.append(format_why_it_matters_block(story.why_it_matters))
    handle_footer = primary_source_handle(sources)
    footer = apply_attribution_to_footer(
        format_source_footer_plain(handle_footer) if handle_footer else None,
        attr,
    )
    if footer:
        parts.append("")
        parts.append(footer)
    if open_loop:
        parts.append("")
        parts.append(open_loop)
    if tags:
        parts.append("")
        parts.append(" ".join(tags))
    if brand_footer:
        parts.append("")
        parts.append(brand_footer)
    use_cta = tuning.structure.include_cta if include_cta is None else include_cta
    if use_cta:
        parts.append("")
        parts.append(_adaptive_cta_line(bucket))
    out = _dedupe_source_lines("\n".join(parts).strip())
    log_event(
        logger,
        "editorial.engagement_applied",
        channel_format="plain",
        bucket=bucket,
        engagement_score=score,
    )
    if len(out) > max_total_chars:
        from app.publisher.draft_builder import complete_story_text

        out = complete_story_text(out, max_chars=max_total_chars)
    return out


def format_source_footer_plain(handle: str | None) -> str:
    tuning = get_editorial_tuning()
    if tuning.attribution.style == "hidden":
        return ""
    h = (handle or "").strip()
    if not h:
        return ""
    if not h.startswith("@"):
        h = f"@{h.lstrip('@')}"
    if tuning.attribution.style == "via":
        return f"via {h}"
    return f"Источник: {h}"


def format_public_post_html(
    content: str,
    sources: str | list[dict[str, Any]] | None = None,
    *,
    draft_id: int | None = None,
    why_it_matters: str | None = None,
    include_cta: bool | None = None,
    runtime_dir: str | None = None,
    max_total_chars: int = 12000,
) -> str:
    _ = draft_id
    tuning = get_editorial_tuning()
    max_body = tuning.structure.summary_max_chars
    polished = _prepare_body_plain(content, max_chars=max_body)
    polished = _strip_embedded_source_lines(polished)
    chans = _parse_source_channels(sources)
    attr = resolve_source_attribution(chans, runtime_dir=runtime_dir)
    if attr.strip_urls_from_body:
        polished = strip_raw_urls(polished)
    use_cta = tuning.structure.include_cta if include_cta is None else include_cta
    bucket = _story_bucket(polished)
    score = _engagement_score(polished, bucket)
    _hl_for_hook, _ = split_headline_and_body(polished)
    hook = _engagement_hook(polished, bucket, headline=_hl_for_hook)
    tags = _smart_hashtags(polished, bucket, runtime_dir=runtime_dir)
    open_loop = _open_loop_line(bucket, score, runtime_dir=runtime_dir, text=polished)
    brand_footer = _adaptive_brand_footer(polished, score)
    if open_loop:
        polished = f"{polished}\n\n{open_loop}"
    from app.editorial.public_post_template import render_public_post_html

    out = render_public_post_html(
        polished,
        sources,
        why_it_matters=why_it_matters,
        signature_line=signature_line_for_now(),
        runtime_dir=runtime_dir,
        intro_hook=hook,
        include_cta=use_cta,
        cta_line=_adaptive_cta_line(bucket),
        hashtags_line=" ".join(tags) if tags else "",
        brand_footer_line=brand_footer,
    )
    log_event(
        logger,
        "editorial.engagement_applied",
        channel_format="html",
        bucket=bucket,
        engagement_score=score,
    )
    if len(out) > max_total_chars:
        out = out[:max_total_chars].rstrip()
    return out
