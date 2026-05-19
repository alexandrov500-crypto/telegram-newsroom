from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F600-\U0001F64F"
    "]+",
    flags=re.UNICODE,
)
_REFERRAL_RE = re.compile(
    r"(?i)(join\s+@|subscribe\s+@|t\.me/\+|promo\s+code|referral\s+link)",
)
_URL_RE = re.compile(r"https?://\S+")


@dataclass(frozen=True, slots=True)
class NormalizedTelegramMessage:
    title: str
    text: str
    source: str
    channel_key: str
    message_id: int
    link: str
    published: datetime | None
    media_type: str = "none"
    media_url: str | None = None
    thumbnail_url: str | None = None
    media_width: int | None = None
    media_height: int | None = None


def _collapse_emojis(text: str) -> str:
    collapsed = _EMOJI_RE.sub(" ", text)
    return re.sub(r"\s{2,}", " ", collapsed).strip()


def normalize_telegram_text(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _collapse_emojis(text.strip())
    if not text:
        return None
    if _REFERRAL_RE.search(text):
        return None
    return text


def title_from_text(text: str, *, max_len: int = 160) -> str:
    first_line = text.split("\n", 1)[0].strip()
    candidate = first_line if first_line else text
    if len(candidate) <= max_len:
        return candidate
    return candidate[: max_len - 1].rstrip() + "…"


def build_telegram_link(channel_key: str, message_id: int) -> str:
    key = channel_key.strip()
    if key.startswith("-100"):
        internal = key[4:]
        return f"https://t.me/c/{internal}/{message_id}"
    username = key.lstrip("@")
    return f"https://t.me/{username}/{message_id}"


def normalize_channel_ref(raw: str) -> str | None:
    token = raw.strip()
    if not token:
        return None
    if token.startswith("https://t.me/"):
        token = token.rstrip("/").split("/")[-1]
    if token.startswith("@"):
        username = token[1:].lower()
        return f"@{username}" if username else None
    if token.startswith("-100") and token[1:].isdigit():
        return token
    if token.lstrip("-").isdigit():
        return token if token.startswith("-") else f"-100{token}"
    if re.fullmatch(r"[A-Za-z0-9_]{3,}", token.lstrip("@")):
        return f"@{token.lstrip('@').lower()}"
    return None


def message_to_normalized(
    *,
    text: str | None,
    channel_display: str,
    channel_key: str,
    message_id: int,
    published: datetime | None = None,
) -> NormalizedTelegramMessage | None:
    normalized = normalize_telegram_text(text)
    if not normalized:
        return None
    if len(normalized) < 20:
        return None
    title = title_from_text(normalized)
    if not title:
        return None
    return NormalizedTelegramMessage(
        title=title,
        text=normalized,
        source=channel_display,
        channel_key=channel_key,
        message_id=message_id,
        link=build_telegram_link(channel_key, message_id),
        published=published or datetime.now(timezone.utc),
    )
