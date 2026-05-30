"""Detect posts that are not publishable as standalone channel text."""

from __future__ import annotations

import re

_INCOMPLETE_TEASER = re.compile(
    r"(выглядят\s+так|выглядит\s+так|смотрите\s+(ниже|выше|картин|график)|"
    r"на\s+(фото|картинке|слайде|инфографик|иллюстрации)|"
    r"продолжение\s+(ниже|в\s+канале)|читайте\s+ниже|"
    r"as\s+shown|see\s+below|details\s+below|read\s+more|in\s+the\s+chart)\s*\.?\s*$",
    re.I,
)
_DEICTIC_STUB = re.compile(r"\b(так|ниже|выше)\s*\.?\s*$", re.I)
_UNFINISHED_ENDING = re.compile(
    r"(\.\.\.|…|[,;:]\s*|[-–—]\s*|и\s*$|или\s*$|а\s*$|но\s*$)\s*$",
    re.I,
)
# Model/source cut-off disguised as a full sentence (… stripped → «для армянского.»).
_TRUNCATED_TAIL = re.compile(
    r"(?:,\s*)?(?:что|котор\w*|когда)\s+[^.!?]{0,160}\b\w+(?:ского|ского|ного|ной|ному|ными)\.\s*$",
    re.I,
)
_INCOMPLETE_FOR_PHRASE = re.compile(r"\bдля\s+\w+(?:ского|ского|ного|ной|ному|ными)\.\s*$", re.I)
_SENTENCE_END = re.compile(r"[.!?]\s*$")
_BUREAUCRATIC = re.compile(
    r"(приказ(ом)?|утвержден(а|о|ы)?\s+форма|предписани|в\s+соответствии\s+с|"
    r"территори(и|я)\s+российской|ведомств|регламент|процедур|уведомлени)",
    re.I,
)
_IMPLICATION = re.compile(
    r"(это\s+значит|почему\s+это\s+важно|влиян|давлен|риск|издержк|ликвидност|"
    r"доходност|волатильн|рынк|экспорт|импорт|инвест|капитал|логистик|усилит|снижени[ея]|рост)",
    re.I,
)
_SIGNAL_DOMAIN = re.compile(
    r"(market|рынк|эконом|финанс|macro|крипт|crypto|геополит|технолог|ai|it|"
    r"ставк|инфляц|цб|фрс|fed|ecb|etf|акци|облигац|экспорт|импорт|логистик|поставк)",
    re.I,
)
_AD_MARKER = re.compile(
    r"(промокод|promo\s*code|реф(?:еральн|erral)|партн[её]рск|sponsored|ad\s*:\s*|"
    r"рекламн|affiliate|utm_|ref=|coupon|скидк[аи]\s+по\s+коду|"
    r"переходите\s+по\s+ссылке|подписывайтесь\s+на\s+наш\s+канал|купить\s+сейчас|buy\s+now)",
    re.I,
)
# Undisclosed native ads: news-shaped teaser that funnels to paid/premium channels.
_PREMIUM_FUNNEL = re.compile(
    r"(?:"
    r"полный\s+разбор\s*[—–\-:]?\s*в\s+(?:premium|платн|закрыт|vip|private)"
    r"|premium[\-\s]?канал(?:е|а)?"
    r"|(?:в\s+)?(?:premium|vip|закрыт(?:ом|ый)?|платн(?:ом|ый)?)\s+канал(?:е|а)?"
    r"|продолжение\s+(?:читайте\s+)?(?:в\s+)?(?:premium|vip|закрыт|платн)"
    r"|подробност(?:и|ь)\s*[—–\-]\s*(?:в\s+)?(?:premium|закрыт|платн|vip|telegram\s+premium)"
    r"|full\s+(?:analysis|breakdown|story)\s*[—\-:]\s*(?:in\s+)?(?:premium|paid|private)"
    r"|read\s+(?:more|the\s+rest)\s+(?:in\s+)?(?:premium|paid|private|members)"
    r"|(?:exclusive|members\s+only)\s+(?:in\s+)?(?:premium|paid|private)"
    r"|(?:subscribe|подпиш(?:итесь|ись))\s+(?:to\s+)?(?:premium|vip|закрыт)"
    r")",
    re.I,
)
_PAYWALL_TEASER = re.compile(
    r"(?:\.\.\.|…)\s*(?:полный|продолжение|подробност|читайте|details|full\s+story).{0,100}"
    r"(?:premium|закрыт|vip|платн|подпис)",
    re.I | re.DOTALL,
)
_URL_WITH_TRACKING = re.compile(r"https?://\S*(?:utm_|ref=|aff|partner)\S*", re.I)
_SIGNATURE_PREFIX = re.compile(
    r"^(5-Minute Macro|Market Pulse|Closing Bell|Alpha Flow)\s+",
    re.I,
)
_ENGAGEMENT_HOOK = re.compile(
    r"(Главное для экономики|Ключевой сигнал(?: для крипторынка)?|Ключевой факт|"
    r"Что важно в геоповестке|Что это значит для рынка)\s*:\s*[^.!?]+[.!?]\s*",
    re.I,
)
_OPEN_LOOP = re.compile(
    r"(Traders now focus|Watch closely|AI rally continues|"
    r"Geopolitical pressure continues|Macro stress continues|"
    r"Crypto risk-on continues)[^.!?]*[.!?]\s*",
    re.I,
)
_SOURCE_FOOTER = re.compile(r"\s*(Источник|Source|via)\s*:\s*@?\S+\s*", re.I)
_TRAILING_HASHTAGS = re.compile(r"\s*(?:#\w+\s*)+$")
_BRAND_CTA = re.compile(
    r"\s*(Follow for high-signal[^.!?]*[.!?]?|Подписывайтесь[^.!?]*[.!?]?)\s*$",
    re.I,
)


def strip_public_template_metadata(text: str) -> str:
    """Remove growth/template chrome before editorial quality checks."""
    t = re.sub(r"\s+", " ", (text or "").strip())
    t = _SIGNATURE_PREFIX.sub("", t).strip()
    t = _ENGAGEMENT_HOOK.sub("", t)
    t = _OPEN_LOOP.sub("", t).strip()
    t = _SOURCE_FOOTER.sub(" ", t).strip()
    t = _TRAILING_HASHTAGS.sub("", t).strip()
    t = _BRAND_CTA.sub("", t).strip()
    return re.sub(r"\s+", " ", t).strip()


def strip_dangling_ellipsis(text: str) -> str:
    t = (text or "").strip()
    t = re.sub(r"(\.\.\.|…)\s*$", "", t).rstrip()
    t = re.sub(r"[,;:]\s*$", "", t).rstrip()
    return t


def _sentence_count(text: str) -> int:
    parts = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    return len([p for p in parts if len(p.strip()) > 12])


def is_publishably_informative(
    text: str,
    *,
    min_chars: int = 100,
    min_sentences: int = 2,
) -> bool:
    """
    Channel post must be a finished thought: no trailing ellipsis, enough substance.
    Premium baseline: at least two meaningful sentences.
    """
    t = strip_dangling_ellipsis(text or "")
    if not t:
        return False
    if _UNFINISHED_ENDING.search(t):
        return False
    if not _SENTENCE_END.search(t):
        return False
    sents = _sentence_count(t)
    if sents < max(1, min_sentences):
        # Premium newsroom baseline: at least two meaningful sentences.
        return False
    return len(t) >= min_chars


def is_truncated_mid_thought(text: str) -> bool:
    """Detect ellipsis-truncated or fake-completed cut-offs (YandexGPT / source teasers)."""
    t = (text or "").strip()
    if not t:
        return True
    if re.search(r"(\.\.\.|…)\s*$", t):
        return True
    if _INCOMPLETE_FOR_PHRASE.search(t):
        return True
    if _TRUNCATED_TAIL.search(t):
        return True
    return False


def is_incomplete_teaser(text: str) -> bool:
    """
    Source post refers to image/chart («выглядят так») without extractable body.
    Such items must not ship as public channel posts with only a headline.
    """
    t = (text or "").strip()
    if not t:
        return True
    if is_truncated_mid_thought(t):
        return True
    if _INCOMPLETE_TEASER.search(t):
        return True
    # Explicitly block dangling endings ("...", trailing comma/colon/dash/conjunction).
    if _UNFINISHED_ENDING.search(t):
        return True
    if len(t) < 200 and _DEICTIC_STUB.search(t):
        sents = [p for p in re.split(r"(?<=[.!?])\s+", t) if len(p.strip()) > 8]
        if len(sents) <= 1:
            return True
    return False


def passes_premium_newsroom_policy(text: str) -> bool:
    """
    Hard policy for publish feed quality:
    - finished narrative (handled by informative checks),
    - no procedural bureaucracy without context,
    - explicit implication for reader/market.
    """
    t = (text or "").strip()
    if not is_publishably_informative(t, min_chars=90, min_sentences=2):
        return False
    if not _SIGNAL_DOMAIN.search(t):
        return False
    # Bureaucratic notices require explicit implication; otherwise drop as filler.
    if _BUREAUCRATIC.search(t) and not _IMPLICATION.search(t):
        return False
    # Even non-bureaucratic posts should explain consequence/importance.
    if not _IMPLICATION.search(t):
        return False
    return True


def has_hidden_advertising(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _AD_MARKER.search(t):
        return True
    if _PREMIUM_FUNNEL.search(t):
        return True
    if _PAYWALL_TEASER.search(t):
        return True
    if _URL_WITH_TRACKING.search(t):
        return True
    return False
