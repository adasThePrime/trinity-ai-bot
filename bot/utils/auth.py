from __future__ import annotations

from functools import wraps
import logging

from aiogram.types import CallbackQuery, ChosenInlineResult, InlineQuery, Message

from bot.services.access import can_use_bot, is_admin, is_user_approved
from bot.services.db import db
from bot.services.cache import cache

logger = logging.getLogger(__name__)


def get_user_id(
    event: CallbackQuery | ChosenInlineResult | InlineQuery | Message
) -> int | None:
    return event.from_user.id if event.from_user else None


def get_chat_id(event: Message | CallbackQuery) -> int | None:
    if isinstance(event, Message):
        return event.chat.id
    elif isinstance(event, CallbackQuery):
        return event.message.chat.id
    return None


async def _deny(
    event: CallbackQuery | ChosenInlineResult | InlineQuery | Message,
    reason: str
):
    if isinstance(event, Message):
        await event.reply(reason)
    elif isinstance(event, CallbackQuery):
        await event.answer(reason)
    elif isinstance(event, InlineQuery):
        await event.answer([], cache_time=0, is_personal=True)
    elif isinstance(event, ChosenInlineResult):
        await event.bot.edit_message_text(
            reason,
            inline_message_id=event.inline_message_id,
            reply_markup=None
        )


async def _check_access(
        event: CallbackQuery | ChosenInlineResult | InlineQuery | Message,
        admin_only: bool,
        approve_only: bool
    ):
    user_id = get_user_id(event)

    if admin_only:
        if not is_admin(user_id):
            await _deny(event, "This action is restricted to admins.")
            return False
    elif approve_only:
        if not is_admin(user_id) and not (user_id and await is_user_approved(user_id)):
            await _deny(event, "Only approved users can use this.")
            return False
    else:
        chat_id = get_chat_id(event) if isinstance(event, (Message, CallbackQuery)) else None
        if not await can_use_bot(user_id, chat_id):
            await _deny(event, "Only approved users can use this.")
            return False
    
    if user_id and cache.should_touch(user_id):
        await db.touch_user(user_id)
        cache.mark_touched(user_id)
        logger.debug(f"Touched user {user_id}")
    
    return True


def ensure_user_access(*, admin_only: bool = False, approve_only: bool = False) -> int | None:
    def decorator(handler):
        @wraps(handler)
        async def wrapper(
            event: CallbackQuery | ChosenInlineResult | InlineQuery | Message,
            *args,
            **kwargs
        ):
            allowed = await _check_access(event, admin_only=admin_only, approve_only=approve_only)
            if not allowed:
                return
            return await handler(event, *args, **kwargs)
        
        return wrapper
    
    return decorator