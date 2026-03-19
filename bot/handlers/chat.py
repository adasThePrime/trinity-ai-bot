from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.config import STREAM_ENABLED
from bot.services.ai import chat_completion, chat_completion_stream, resolve_user_model
from bot.services.db import db
from bot.services.rate_limit import enforce_rate_limit
from bot.services.streaming import stream_response
from bot.services.typing import typing_manager
from bot.utils.auth import ensure_user_access
from bot.utils.context import add_message, get_history, inject_reply
from bot.utils.errors import error_detail
from bot.utils.formatting import parse_entities, split_with_entities, trim_to_limit
from bot.utils.prompts import build_system_prompt

logger = logging.getLogger(__name__)
router = Router(name="chat")


async def _send_long_response(message: Message, text: str):
    plain, entities = parse_entities(text)
    chunks = split_with_entities(plain, entities)

    if len(chunks) > 2:
        chunks = chunks[:2]
        last_text, last_ents = chunks[-1]
        chunks[-1] = trim_to_limit(last_text, last_ents)

    for chunk_text, chunk_entities in chunks:
        await message.reply(
            chunk_text,
            entities=chunk_entities if chunk_entities else None,
            parse_mode=None,
            disable_web_page_preview=True
        )


async def _process_classic_message(
    message: Message,
    chat_id: int,
    full_messages: list[dict],
    model: str
):
    async with typing_manager.typing(chat_id, message.chat):
        try:
            reply_text = await chat_completion(full_messages, model=model)
        except Exception as exc:
            logger.exception(f"AI completion failed for chat {chat_id}")
            detail = error_detail(exc)
            await message.reply(
                "Something went wrong while generating a response. Please try again.\n\n"
                f"{detail}"
            )
            return

    if not reply_text:
        await message.reply(
            "I couldn't generate a response. Please try again.\n\n"
            "Empty response from AI model"
        )
        return
    
    add_message(chat_id, "assistant", reply_text)
    await _send_long_response(message, reply_text)


async def _process_streaming_message(
    message: Message,
    chat_id: int,
    full_messages: list[dict],
    model: str
):
    async with typing_manager.typing(chat_id, message.chat):
        try:
            text_stream = chat_completion_stream(full_messages, model)
            reply_text = await stream_response(
                message.bot,
                chat_id,
                text_stream,
                reply_to_message_id=message.message_id
            )
        except Exception as exc:
            logger.exception(f"Streaming AI completion failed for chat {chat_id}")
            detail = error_detail(exc)
            await message.reply(
                "Something went wrong while generating a response. Please try again.\n\n"
                f"{detail}"
            )
            return

    if not reply_text:
        await message.reply(
            "I couldn't generate a response. Please try again.\n\n"
            "Empty response from AI model"
        )
        return

    logger.debug(f"Chat {chat_id}: streamed response {len(reply_text)} chars")
    add_message(chat_id, "assistant", reply_text)


async def _should_stream(user_id: int, chat_type: ChatType) -> bool:
    if not STREAM_ENABLED:
        return False
    if chat_type != ChatType.PRIVATE:
        return False
    return await db.get_user_streaming_preference(user_id)


async def _process_user_prompt(message: Message) -> str:
    user_id = message.from_user.id

    me = await message.bot.me()
    chat_id = message.chat.id
    user_text = (message.text or "").strip()

    if not user_text:
        return
    
    if message.reply_to_message and message.reply_to_message.text:
        inject_reply(chat_id, message.reply_to_message.text)
    
    add_message(chat_id, "user", user_text)

    system_prompt = build_system_prompt(me.username)
    full_messages = [
        {"role": "system", "content": system_prompt},
        *get_history(chat_id)
    ]

    model = await resolve_user_model(user_id)
    use_streaming = await _should_stream(user_id, message.chat.type)
    
    logger.debug(
        f"Chat {chat_id}: model={model} streaming={use_streaming} "
        f"prompt_len={len(user_text)}"
    )

    if use_streaming:
        await _process_streaming_message(message, chat_id, full_messages, model)
    else:
        await _process_classic_message(message, chat_id, full_messages, model)


@router.message(F.chat.type == ChatType.PRIVATE, F.text, ~F.via_bot)
@ensure_user_access()
@enforce_rate_limit()
async def handle_private(message: Message):
    await _process_user_prompt(message)


@router.message(
    F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}),
    F.text,
    ~F.via_bot
)
@ensure_user_access()
@enforce_rate_limit()
async def handle_group(message: Message):    
    me = await message.bot.me()
    mention = f"@{me.username}".lower()

    is_mentioned = mention in (message.text or "").lower()
    is_reply_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id == me.id
    )

    if not is_mentioned and not is_reply_to_bot:
        return

    await _process_user_prompt(message)