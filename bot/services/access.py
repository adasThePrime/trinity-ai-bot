from __future__ import annotations

import logging

from bot.config import ADMIN_IDS
from bot.services.cache import cache
from bot.services.db import db

logger = logging.getLogger(__name__)


async def _is_approved_cached(chat_id: int) -> bool:
    entry = cache.get_user(chat_id)
    if entry is not None and entry.is_approved is not None:
        return entry.is_approved

    approved = await db.is_chat_approved(chat_id)
    user_entry = cache.ensure_user(chat_id)
    user_entry.is_approved = approved
    logger.debug(f"Cached approval for {chat_id}: {approved}")
    return approved


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in ADMIN_IDS


async def can_use_bot(user_id: int | None, chat_id: int | None) -> bool:
    if user_id and is_admin(user_id):
        return True

    if not cache.approve_only_mode:
        return True

    if user_id and await _is_approved_cached(user_id):
        return True

    if chat_id and chat_id != user_id and await _is_approved_cached(chat_id):
        return True

    logger.debug(f"Access denied: user={user_id} chat={chat_id} approve_only={cache.approve_only_mode}")
    return False


async def is_user_approved(user_id: int) -> bool:
    return await _is_approved_cached(user_id)