from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

from bot.config import STREAM_ENABLED
from bot.services.ai import (
    alias_to_model_id,
    get_models,
    resolve_user_model,
    valid_model_id
)
from bot.services.access import is_user_approved
from bot.services.db import db
from bot.utils.auth import ensure_user_access, get_user_id
from bot.utils.messages import (
    build_models_message,
    build_settings_message,
    build_streaming_message,
    build_usage_message
)

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


async def _safe_callback_message_edit(callback: CallbackQuery, text: str, markup=None):
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest as exc:
        if "not modified" in str(exc).lower():
            logger.debug(f"Message not modified for user {get_user_id(callback)}, ignoring")
        else:
            logger.warning(f"Failed to edit message: {exc}")
            raise


@router.callback_query(F.data.startswith("model:"))
@ensure_user_access()
async def cb_model_select(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    alias = callback.data[len("model:"):]
    model_id = alias_to_model_id(alias)

    if not valid_model_id(model_id):
        logger.debug(f"User {user_id} tried unavailable model alias '{alias}'")
        await callback.answer("This model is no longer available.", show_alert=True)
        return
    
    await db.set_user_model(user_id, model_id)
    logger.debug(f"User {user_id} switched model to '{model_id}'")

    current_model = await resolve_user_model(user_id)
    text, markup = build_models_message(current_model)
    selected_name = next(
        (m["name"] for m in get_models() if m["id"] == model_id), model_id
    )

    await _safe_callback_message_edit(callback, text, markup)
    await callback.answer(f"Switched to {selected_name}")


@router.callback_query(F.data == "settings:back")
@ensure_user_access()
async def cb_settings_back(callback: CallbackQuery):    
    text, markup = build_settings_message()
    await _safe_callback_message_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "settings:models")
@ensure_user_access()
async def cb_settings_models(callback: CallbackQuery):
    user_id = callback.from_user.id

    current = await resolve_user_model(user_id)
    text, markup = build_models_message(current)

    await _safe_callback_message_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data.in_({"settings:usage", "settings:usage_refresh"}))
@ensure_user_access()
async def cb_settings_usage(callback: CallbackQuery):
    user_id = callback.from_user.id

    approved = await is_user_approved(user_id)
    counts = await db.get_usage_stats(user_id, approved)
    text, markup = build_usage_message(user_id, counts)

    await _safe_callback_message_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "settings:streaming")
@ensure_user_access()
async def cb_settings_streaming(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    user_pref = await db.get_user_streaming_preference(user_id)
    text, markup = build_streaming_message(user_pref)

    await _safe_callback_message_edit(callback, text, markup)
    await callback.answer()


@router.callback_query(F.data == "settings:streaming_toggle")
@ensure_user_access()
async def cb_settings_streaming_toggle(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    if not STREAM_ENABLED:
        await callback.answer("Feature disabled by the admin.", show_alert=True)
        return

    current = await db.get_user_streaming_preference(user_id)
    new_pref = not current

    await db.set_user_streaming_preference(user_id, new_pref)
    logger.info(f"User {user_id} {'enabled' if new_pref else 'disabled'} streaming")

    text, markup = build_streaming_message(new_pref)

    await _safe_callback_message_edit(callback, text, markup)
    await callback.answer()


@router.callback_query()
async def cb_unknown(callback: CallbackQuery):
    await callback.answer()