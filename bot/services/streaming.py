from __future__ import annotations

import logging
import random
import time

from aiogram import Bot
from aiogram.types import ReplyParameters

from bot.config import STREAM_CHUNK_SIZE, STREAM_DRAFT_INTERVAL
from bot.utils.formatting import parse_entities, split_with_entities, trim_to_limit

logger = logging.getLogger(__name__)

_DRAFT_ID_MAX = 2**31 - 1


async def _send_draft(bot: Bot, chat_id: int, draft_id: int, raw_text: str):
    try:
        plain, entities = parse_entities(raw_text)
        plain, entities = trim_to_limit(plain, entities)
        await bot.send_message_draft(
            chat_id=chat_id,
            draft_id=draft_id,
            text=plain,
            entities=entities if entities else None
        )
    except Exception:
        logger.debug("send_message_draft failed (non-critical)", exc_info=True)


async def _send_confirmed(bot: Bot, chat_id: int, raw_text: str, reply_to_message_id: int | None):
    plain, entities = parse_entities(raw_text)
    chunks = split_with_entities(plain, entities)

    if len(chunks) > 2:
        chunks = chunks[:2]
        last_text, last_ents = chunks[-1]
        chunks[-1] = trim_to_limit(last_text, last_ents)

    for i, (chunk_text, chunk_entities) in enumerate(chunks):
        reply_params = {}
        if i == 0 and reply_to_message_id is not None:
            reply_params["reply_parameters"] = ReplyParameters(
                message_id=reply_to_message_id
            )

        await bot.send_message(
            chat_id=chat_id,
            text=chunk_text,
            entities=chunk_entities if chunk_entities else None,
            parse_mode=None,
            disable_web_page_preview=True,
            **reply_params
        )


async def stream_response(
    bot: Bot,
    chat_id: int,
    text_stream,
    reply_to_message_id=None
):
    draft_id = random.randint(1, _DRAFT_ID_MAX)
    accumulated = ""
    last_draft_time = 0.0
    last_draft_len = 0

    
    async for chunk in text_stream:
        accumulated += chunk
        now = time.monotonic()

        new_chars = len(accumulated) - last_draft_len
        elapsed = now - last_draft_time

        if new_chars >= STREAM_CHUNK_SIZE and elapsed >= STREAM_DRAFT_INTERVAL:
            await _send_draft(bot, chat_id, draft_id, accumulated)
            last_draft_time = time.monotonic()
            last_draft_len = len(accumulated)

    if not accumulated:
        return ""

    await _send_draft(bot, chat_id, draft_id, accumulated)
    await _send_confirmed(bot, chat_id, accumulated, reply_to_message_id)

    logger.info(f"Stream complete: {len(accumulated)} chars")
    return accumulated