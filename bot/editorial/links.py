from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_STRIP_QUERY_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref", "ocid")
_STRIP_QUERY_EXACT = frozenset(
    {
        "pilot",
        "canary_e2e",
        "cmpid",
        "smid",
        "s",
    },
)


def canonical_article_url(link: str) -> str:
    """Normalize article URL for display and Telegram previews."""
    raw = (link or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw
    if not parsed.scheme:
        return raw

    kept: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        kl = key.lower()
        if kl in _STRIP_QUERY_EXACT:
            continue
        if any(kl.startswith(p) for p in _STRIP_QUERY_PREFIXES):
            continue
        kept.append((key, value))

    clean = parsed._replace(query=urlencode(kept), fragment="")
    return urlunparse(clean)
