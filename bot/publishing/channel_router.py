from __future__ import annotations

import logging

from bot.processing.languages import LANG_EN, normalize_language_code
from bot.publisher import ChannelPublisher

logger = logging.getLogger(__name__)


class ChannelRouter:
    """Map language codes to Telegram channel IDs."""

    def __init__(
        self,
        publisher: ChannelPublisher,
        channel_by_language: dict[str, int],
        *,
        default_channel_id: int | None = None,
    ) -> None:
        self._publisher = publisher
        self._channel_by_language = dict(channel_by_language)
        self._default_channel_id = default_channel_id

    def channel_for(self, language: str | None) -> int | None:
        lang = normalize_language_code(language) or LANG_EN
        channel_id = self._channel_by_language.get(lang)
        if channel_id is not None:
            return channel_id
        if self._default_channel_id is not None:
            return self._default_channel_id
        return self._publisher.channel_id

    def configured_languages(self) -> list[str]:
        return sorted(self._channel_by_language.keys())

    @property
    def publisher(self) -> ChannelPublisher:
        return self._publisher
