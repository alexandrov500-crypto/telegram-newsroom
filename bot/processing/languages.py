from __future__ import annotations

LANG_RU = "ru"
LANG_EN = "en"

SUPPORTED_LANGUAGES: tuple[str, ...] = (LANG_RU, LANG_EN)

PRIMARY_CHANNELS_ENV_PREFIX = "TELEGRAM_CHANNEL_"

LANGUAGE_LABELS: dict[str, str] = {
    LANG_RU: "Russian",
    LANG_EN: "English",
}

DEFAULT_SOURCE_LANGUAGE = LANG_EN
DEFAULT_ENABLED_LANGUAGES: frozenset[str] = frozenset({LANG_RU, LANG_EN})


def normalize_language_code(raw: str | None) -> str | None:
    if not raw:
        return None
    code = str(raw).strip().lower().replace("_", "-").split("-")[0]
    if code in SUPPORTED_LANGUAGES:
        return code
    return None


def is_supported_language(code: str | None) -> bool:
    return normalize_language_code(code) is not None
