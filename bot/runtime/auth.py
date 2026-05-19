from __future__ import annotations

import logging

from aiogram.types import Message, TelegramObject

logger = logging.getLogger(__name__)

_admin_user_ids: frozenset[int] = frozenset()


def configure_admin_access(admin_user_ids: frozenset[int]) -> None:
    global _admin_user_ids
    _admin_user_ids = admin_user_ids
    if admin_user_ids:
        logger.info("Admin access configured for user_ids=%s", sorted(admin_user_ids))
    else:
        logger.warning("ADMIN_USER_IDS empty; all control commands will deny access")


async def is_admin(update: Message | TelegramObject) -> bool:
    user = None
    if isinstance(update, Message):
        user = update.from_user
    elif hasattr(update, "from_user"):
        user = getattr(update, "from_user", None)

    if user is None:
        return False
    return user.id in _admin_user_ids
