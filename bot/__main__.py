from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.config import (
    BOT_TOKEN,
    INLINE_QUERY_ENABLED,
    LOG_LEVEL,
    LOG_LEVELS,
    MAINTENANCE_MODE
)
from bot.handlers import callbacks, chat, commands, inline
from bot.middlewares import MaintenanceMiddleware
from bot.services.cache import load_startup_data
from bot.services.db import db
from bot.services.http import close_all_http_clients

logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s"
    )
for _name, _level in LOG_LEVELS.items():
    logging.getLogger(_name).setLevel(getattr(logging, _level, logging.INFO))
logger = logging.getLogger(__name__)


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher()

    if MAINTENANCE_MODE:
        logger.warning("Maintenance mode is ENABLED — all updates will be intercepted")
        dp.message.outer_middleware(MaintenanceMiddleware())
        dp.callback_query.outer_middleware(MaintenanceMiddleware())
        dp.inline_query.outer_middleware(MaintenanceMiddleware())
        dp.chosen_inline_result.outer_middleware(MaintenanceMiddleware())
    else:
        dp.include_router(commands.router)
        dp.include_router(callbacks.router)
        dp.include_router(chat.router)
        if INLINE_QUERY_ENABLED:
            dp.include_router(inline.router)

    try:
        logger.info("Trinity AI is starting...")
        if not MAINTENANCE_MODE:
            await db.connect()
            await load_startup_data()
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logger.info("Interrupt signal received.")
    finally:
        await db.close()
        await close_all_http_clients()
        logger.info("Trinity AI has shut down.")
    

try:
    import uvloop # pyright: ignore[reportMissingImports]
    logger.info("uvloop is available, using it.")
    uvloop.run(main())
except ImportError:
    logger.info("uvloop unavailable, using asyncio.")
    asyncio.run(main())