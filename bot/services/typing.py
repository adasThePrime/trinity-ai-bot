from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from aiogram.enums import ChatAction
from aiogram.types import Chat

from bot.config import TYPING_STATUS_INTERVAL

logger = logging.getLogger(__name__)


class _ChatEntry:
    __slots__ = ("count", "task", "stop")

    def __init__(self):
        self.count: int = 0
        self.task: asyncio.Task | None = None
        self.stop: asyncio.Event = asyncio.Event()


class TypingManager:
    def __init__(self):
        self._chats: dict[int, _ChatEntry] = {}
        
    @asynccontextmanager
    async def typing(self, chat_id: int, chat: Chat):
        entry = self._chats.setdefault(chat_id, _ChatEntry())
        entry.count += 1

        if entry.count == 1:
            entry.stop.clear()
            entry.task = asyncio.create_task(
                self._keep_typing(chat, entry.stop)
            )
            logger.debug(f"Typing loop started for chat {chat_id}")

        try:
            yield
        finally:
            entry.count -= 1
            if entry.count == 0:
                entry.stop.set()
                if entry.task is not None:
                    await entry.task
                self._chats.pop(chat_id, None)
                logger.debug(f"Typing loop stopped for chat {chat_id}")

    @staticmethod
    async def _keep_typing(chat: Chat, stop: asyncio.Event):
        while not stop.is_set():
            try:
                await chat.do(ChatAction.TYPING)
            except Exception:
                pass
        try:
            await asyncio.wait_for(
                stop.wait(), timeout=TYPING_STATUS_INTERVAL
            )
        except asyncio.TimeoutError:
            pass


typing_manager = TypingManager()