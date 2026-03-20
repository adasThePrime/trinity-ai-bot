from __future__ import annotations

import logging
import secrets

from aiogram import Router
from aiogram.types import (
    ChosenInlineResult,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent
)

from bot.services.ai import chat_completion, resolve_user_model
from bot.services.rate_limit import enforce_rate_limit
from bot.utils.auth import ensure_user_access
from bot.utils.errors import error_detail
from bot.utils.formatting import parse_entities, trim_to_limit
from bot.utils.prompts import build_system_prompt

logger = logging.getLogger(__name__)
router = Router(name="inline")


@router.inline_query()
@ensure_user_access()
async def handle_inline_query(inline_query: InlineQuery):
    me = await inline_query.bot.get_me()
    text = (inline_query.query or "").strip()

    if not text:
        article = InlineQueryResultArticle(
            id="empty_query",
            title="Ask Trinity",
            input_message_content=InputTextMessageContent(
                message_text=f"Type your question after <code>@{me.username}</code> in the chat!"
            ),
            description="Type your prompt to get a response from Trinity."
        )
        await inline_query.answer(results=[article], cache_time=86400)
        return
    
    article = InlineQueryResultArticle(
        id=f"prompt_preview:{secrets.token_urlsafe(16)}",
        title="Ask Trinity",
        input_message_content=InputTextMessageContent(
            message_text="Thinking...",
        ),
        description=text[:256],
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⏳", callback_data="noop")]
            ]
        )
    )

    await inline_query.answer(results=[article], cache_time=86400)


@router.chosen_inline_result()
@ensure_user_access()
@enforce_rate_limit()
async def handle_chosen_inline_result(chosen_result: ChosenInlineResult):
    user_id = chosen_result.from_user.id
    inline_message_id = chosen_result.inline_message_id
    if not inline_message_id:
        logger.debug(
            f"Rejected chosen inline query without inline message id from user {chosen_result.from_user.id}"
        )
        return

    me = await chosen_result.bot.get_me()
    user_text = (chosen_result.query or "").strip()

    if not user_text:
        return
    
    system_prompt = build_system_prompt(me.username)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]
    model = await resolve_user_model(user_id)

    try:
        reply_text = await chat_completion(messages, model)
    except Exception as exc:
        logger.exception("AI completion failed for inline query")
        detail = error_detail(exc)
        await chosen_result.bot.edit_message_text(
            text=f"Something went wrong while generating a response. Please try again.\n\n{detail}",
            inline_message_id=chosen_result.inline_message_id,
            reply_markup=None
        )
        return
    
    if not reply_text:
        logger.warning("AI completion returned empty response for inline query")
        reply_text = "I couldn't generate a response. Please try again."
    
    plain, entities = parse_entities(reply_text)
    plain, entities = trim_to_limit(plain, entities)
    
    await chosen_result.bot.edit_message_text(
        text=plain,
        inline_message_id=chosen_result.inline_message_id,
        entities=entities if entities else None,
        parse_mode=None,
        reply_markup=None,
        disable_web_page_preview=True
    )