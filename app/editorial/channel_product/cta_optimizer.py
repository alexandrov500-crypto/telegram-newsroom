"""CTA optimizer — stable A/B variants with engagement feedback weights."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

_SHARE_VARIANTS: dict[str, list[str]] = {
    "macro": [
        "Перешлите коллеге из финансов — один канал вместо десяти лент.",
        "Сохраните: пригодится тем, кто следит за ставками и макро.",
        "Forward для команды: сжатый сигнал без шума.",
    ],
    "crypto": [
        "Перешлите трейдеру — заменяет 3–5 крипто-каналов.",
        "Сохраните в Saved — быстрый доступ к решению по риску.",
    ],
    "geo": [
        "Перешлите тем, кто следит за геополитикой и рынками.",
        "Forward коллеге: контекст + последствия в одном посте.",
    ],
    "market": [
        "Перешлите инвестору — reference forward вместо скролла лент.",
        "Сохраните: decision input до открытия рынка.",
    ],
    "general": [
        "Перешлите тем, кому актуально — один канал вместо множества подписок.",
        "Сохраните пост — сигнал для решений, не просто новость.",
    ],
}

_SUBSCRIBE_VARIANTS: dict[str, list[str]] = {
    "macro": "Подписывайтесь: macro + markets + AI в одной ленте — без 10–20 каналов.",
    "crypto": "Подписывайтесь: crypto + macro + geopolitics — одна умная лента.",
    "geo": "Подписывайтесь: геополитика + рынки + tech — один канал вместо ленты.",
    "market": "Подписывайтесь: рынки, макро, AI — decision feed без шума.",
    "general": "Подписывайтесь: один канал заменяет 10–20 Telegram-источников.",
}


@dataclass(frozen=True)
class CTAVariant:
    variant_id: str
    share_nudge: str
    subscribe_line: str
    bucket: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "share_nudge": self.share_nudge,
            "subscribe_line": self.subscribe_line,
            "bucket": self.bucket,
        }


def _stable_index(text: str, n: int) -> int:
    if n <= 0:
        return 0
    h = hashlib.md5((text or "").encode("utf-8")).hexdigest()
    return int(h, 16) % n


def _story_bucket(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in ("bitcoin", "btc", "crypto", "крипт", "eth")):
        return "crypto"
    if any(k in t for k in ("sanction", "war", "геополит", "nato", "войн")):
        return "geo"
    if any(k in t for k in ("fed", "cpi", "инфляц", "ставк", "macro", "цб")):
        return "macro"
    if any(k in t for k in ("рынок", "moex", "nasdaq", "акци", "бирж")):
        return "market"
    return "general"


def select_cta_variant(
    text: str,
    *,
    topic_weights: dict[str, float] | None = None,
) -> CTAVariant:
    bucket = _story_bucket(text)
    if topic_weights:
        best = max(topic_weights.items(), key=lambda kv: kv[1], default=(bucket, 0.0))
        if best[1] >= 0.55 and best[0] in _SHARE_VARIANTS:
            bucket = best[0]

    share_opts = _SHARE_VARIANTS.get(bucket, _SHARE_VARIANTS["general"])
    idx = _stable_index(text, len(share_opts))
    share = share_opts[idx]
    sub = _SUBSCRIBE_VARIANTS.get(bucket, _SUBSCRIBE_VARIANTS["general"])
    if isinstance(sub, list):
        sub = sub[0]

    variant_id = f"{bucket}_v{idx}"
    return CTAVariant(variant_id=variant_id, share_nudge=share, subscribe_line=sub, bucket=bucket)
