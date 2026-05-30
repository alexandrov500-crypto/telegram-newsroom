"""@cb_economics reference editorial model — macro RU economics cycle and quality bar."""

from __future__ import annotations

import os
import re

_REFERENCE_MODEL_CB = "cb_economics"

# Peers in the same editorial lane as @cb_economics (macro / business RU, no crypto teasers).
_DEFAULT_REFERENCE_HANDLES = frozenset(
    {
        "@cb_economics",
        "cb_economics",
        "@rbc_news",
        "rbc_news",
        "@vedomosti",
        "vedomosti",
        "@banksta",
        "banksta",
        "@thebell_io",
        "thebell_io",
    }
)

_REFERENCE_CATEGORIES = frozenset({"macro", "market", "breaking", "analysis"})

_CRYPTO_TEASER = re.compile(
    r"(?:"
    r"to\s+the\s+moon|100x|pump\s+soon|"
    r"premium[\-\s]?канал|закрыт(?:ом|ый)?\s+канал|"
    r"полный\s+разбор\s*(?:[—–\-:]\s*)?в\s+(?:premium|платн|закрыт|vip)"
    r")",
    re.I,
)


def _normalize_handle(channel: str) -> str:
    key = (channel or "").strip().lower()
    if not key:
        return ""
    return key if key.startswith("@") else f"@{key.lstrip('@')}"


def reference_model_id() -> str | None:
    """Active reference model id, or None when disabled."""
    raw = os.getenv("NEWSROOM_REFERENCE_MODEL", "").strip().lower()
    if raw in {"", "off", "none", "false", "0", "disabled"}:
        return None
    if raw in {_REFERENCE_MODEL_CB, "cb", "macro"}:
        return _REFERENCE_MODEL_CB
    return raw


def reference_model_enabled() -> bool:
    return reference_model_id() == _REFERENCE_MODEL_CB


def reference_source_handles() -> frozenset[str]:
    raw = os.getenv("NEWSROOM_REFERENCE_SOURCES", "").strip()
    if not raw:
        return _DEFAULT_REFERENCE_HANDLES
    out: set[str] = set()
    for part in raw.replace(";", ",").split(","):
        key = _normalize_handle(part)
        if not key:
            continue
        out.add(key)
        out.add(key.lstrip("@"))
    return frozenset(out) if out else _DEFAULT_REFERENCE_HANDLES


def is_reference_source(channel: str) -> bool:
    key = _normalize_handle(channel)
    if not key:
        return False
    handles = reference_source_handles()
    return key in handles or key.lstrip("@") in handles


def reference_auto_publish_categories() -> frozenset[str]:
    raw = os.getenv("NEWSROOM_REFERENCE_CATEGORIES", "").strip()
    if not raw:
        return _REFERENCE_CATEGORIES
    return frozenset(p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip())


def filter_source_channels(handles: list[str]) -> tuple[str, ...]:
    """When reference model is active, keep only trusted macro handles."""
    if not reference_model_enabled():
        return tuple(handles)
    allowed = reference_source_handles()
    kept: list[str] = []
    for h in handles:
        key = _normalize_handle(h)
        bare = key.lstrip("@")
        if key in allowed or bare in allowed:
            kept.append(h if h.startswith("@") else f"@{bare}")
    return tuple(kept) if kept else tuple(handles[:1])


def reference_fastlane_handles() -> frozenset[str]:
    """Sources eligible for cb-style fast auto-publish."""
    if not reference_model_enabled():
        return frozenset()
    return reference_source_handles()


def reference_model_desk_reject(
    text: str,
    sources: list[str],
    category: str,
) -> str | None:
    """
    Enforce @cb_economics bar at desk triage.
    Returns reason code when the item must not become a draft.
    """
    if not reference_model_enabled():
        return None

    chans = [s for s in (sources or []) if (s or "").strip()]
    if chans and not any(is_reference_source(s) for s in chans):
        return "reference_model_source_not_allowed"

    cat = (category or "").strip().lower()
    if cat not in reference_auto_publish_categories():
        return f"reference_model_category:{cat or 'unknown'}"

    t = (text or "").strip()
    if _CRYPTO_TEASER.search(t):
        return "reference_model_crypto_teaser"

    from app.editorial.content_quality import (
        has_hidden_advertising,
        is_incomplete_teaser,
        is_publishably_informative,
    )

    if has_hidden_advertising(t) or is_incomplete_teaser(t):
        return None  # hard rejects in desk_filter handle these

    min_sents = 1 if cat in {"macro", "market", "breaking", "analysis"} else 2
    min_chars = 40 if cat == "breaking" else 60
    if not is_publishably_informative(t, min_chars=min_chars, min_sentences=min_sents):
        return "reference_model_not_informative"

    return None


def apply_reference_model_env_defaults() -> None:
    """
    Idempotent startup defaults when NEWSROOM_REFERENCE_MODEL=cb_economics.
    Only sets vars that are unset — explicit .env always wins.
    """
    if not reference_model_enabled():
        return
    defaults = {
        "EDITORIAL_OPINION_LAYER_ENABLED": "false",
        "NEWSROOM_PRIMARY_NICHES": "macro,business,finance",
        "NEWSROOM_EXCLUDE_GENERAL_FEED": "true",
        "AUTO_PUBLISH_ALLOWED_CATEGORIES": "macro,market,breaking,analysis",
    }
    from app.editorial.growth_profile import aggressive_growth_enabled

    if not aggressive_growth_enabled():
        defaults.update(
            {
                "GROWTH_SIGNATURE_ENABLED": "false",
                "NEWSROOM_ENGAGEMENT_HOOK_ENABLED": "false",
                "NEWSROOM_OPEN_LOOP_ENABLED": "false",
            }
        )
    fastlane = os.getenv("AUTO_PUBLISH_FASTLANE_SOURCES", "").strip()
    if not fastlane:
        peers = sorted({h for h in reference_source_handles() if h.startswith("@")})
        defaults["AUTO_PUBLISH_FASTLANE_SOURCES"] = ",".join(peers)
    for key, val in defaults.items():
        if not os.getenv(key, "").strip():
            os.environ[key] = val
