from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import (
    CallbackQuery,
    ChosenInlineResult,
    InlineQuery,
    Message,
    TelegramObject
)

from bot.config import MAINTENANCE_MESSAGE


class MaintenanceMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any]
    ):
        if isinstance(event, Message):
            await event.reply(MAINTENANCE_MESSAGE)
        elif isinstance(event, CallbackQuery):
            await event.answer(MAINTENANCE_MESSAGE, show_alert=True)
        elif isinstance(event, InlineQuery):
            await event.answer([], cache_time=0)
        elif isinstance(event, ChosenInlineResult):
            if event.inline_message_id:
                await event.bot.edit_message_text(
                    text=MAINTENANCE_MESSAGE,
                    inline_message_id=event.inline_message_id,
                    reply_markup=None
                )