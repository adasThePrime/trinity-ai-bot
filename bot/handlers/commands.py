from __future__ import annotations

import logging

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.services.access import is_admin
from bot.services.cache import cache, reload_cache
from bot.services.db import db
from bot.utils.auth import ensure_user_access
from bot.utils.context import reset_context
from bot.utils.messages import build_settings_message

logger = logging.getLogger(__name__)
router = Router(name="commands")


@router.message(CommandStart())
@ensure_user_access()
async def cmd_start(message: Message):
    user_id = message.from_user.id

    logger.debug(f"User {user_id} invoked /start")
    me = await message.bot.me()
    keyboard = [
        [InlineKeyboardButton(text="Switch to Inline Mode", switch_inline_query="")],
        [InlineKeyboardButton(text="Add to Group", url=f"https://t.me/{me.username}?startgroup=true&admin=manage_chat")]
    ]

    await message.reply(
        "<b>Hi, I'm Trinity!</b>\n\n"
        "I'm an AI assistant designed to help you with various tasks. "
        "I can also be added to your group, and you can <code>@tag</code> "
        "me whenever you need help.\n\n"
        f"<b>Inline mode:</b>\nType <code>@{me.username} your question</code> in any chat "
        "to get a quick answer without leaving the conversation.\n\n"
        "Send /help to learn more about me!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )


@router.message(Command("help"))
@ensure_user_access()
async def cmd_help(message: Message):
    user_id = message.from_user.id
    
    logger.debug(f"User {user_id} invoked /help")
    text = (
        "<b>Trinity AI - Help</b>\n\n"
        "<b>Commands:</b>\n"
        "<code>/start</code> - Ping the bot\n"
        "<code>/clear</code> - Clear conversation history\n"
        "<code>/settings</code> - Bot settings\n"
        "<code>/privacy</code> - Privacy policy\n"
        "<code>/help</code> - Show help message\n\n"
    )

    user_id = message.from_user.id if message.from_user else None
    if is_admin(user_id):
        text += (
            "<b>Admin Commands:</b>\n"
            "<code>/approve</code> - Approve a user/group (ID, reply, or send in group)\n"
            "<code>/disapprove</code> - Disapprove a user/group\n"
            "<code>/approveonly</code> - Toggle approve-only mode\n"
            "<code>/clearcache</code> - Clear and reload the cache\n\n"
        )

    text += (
        "<b>Usage:</b>\n"
        "• In <b>private chats</b>, simply send any message.\n"
        "• In <b>groups</b>, mention me or reply to one of my messages.\n"
        "• In <b>inline mode</b>, you can ask me anything directly from any chat."
    )

    await message.reply(text)


@router.message(Command("clear"))
@ensure_user_access()
async def cmd_clear(message: Message):
    user_id = message.from_user.id
    
    logger.info(f"User {user_id} invoked /clear in chat {message.chat.id}")
    reset_context(message.chat.id)
    await message.reply("Conversation history has been cleared. Let's start fresh!")


@router.message(Command("settings"))
@ensure_user_access()
async def cmd_settings(message: Message):
    user_id = message.from_user.id
    
    logger.debug(f"User {user_id} invoked /settings")
    text, markup = build_settings_message()
    await message.reply(text, reply_markup=markup)


@router.message(Command("privacy"))
@ensure_user_access()
async def cmd_privacy(message: Message):
    user_id = message.from_user.id
    
    logger.info(f"User {user_id} invoked /privacy")
    await message.reply(
        "<b>Privacy Policy - Trinity AI</b>\n\n"
        "<b>1. Introduction</b>\n"
        "This Privacy Policy explains how your data is handled when you interact with this AI-"
        "powered Telegram chatbot. By using this bot, you agree to the terms described below.\n\n"
        "<b>2. Data We Collect</b>\n"
        "We only access your Telegram username/ID, the messages you send, message timestamps, "
        "and interaction patterns. Timestamps and interaction patterns are used solely to detect "
        "and prevent abuse, spam, and misuse of the bot.\n\n"
        "<b>3. Date Retention</b>\n"
        "We do not store your conversations in any database. All chat history is kept in temporary "
        "memory only, and is permanently deleted when the bot restarts or when you send <code>/clear</code>.\n\n"
        "<b>4. Third-Party AI Providers</b>\n"
        "This bot uses third-party AI services to generate responses. Your messages are transmitted "
        "to these providers, who may retain or use them to train their models. We do not control their "
        "data practices.\n\n"
        "<b>5. Children Safety</b>\n"
        "While we do our best to configure the AI to avoid generating NSFW or harmful content, AI models are "
        "not fully predictable and may occasionally produce unexpected responses. Adult supervision is strongly recommended.\n\n"
        "<b>6. Policy Changes</b>\n"
        "This policy may be updated at any time. Continued use implies acceptance."
    )


def _parse_target_id(message: Message) -> int | None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) > 1:
        try:
            return int(parts[1].strip())
        except ValueError:
            return None
        
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id
    
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        return message.chat.id
    
    return None


@router.message(Command("approve"))
@ensure_user_access(admin_only=True)
async def cmd_approve(message: Message):
    user_id = message.from_user.id
    
    target = _parse_target_id(message)
    if target is None:
        await message.reply(
            "Send <code>/approve</code> with a chat id, reply to a user, "
            "or send in a group to approve it."
        )
        return
    
    await db.add_approved_chat(target)
    cache.invalidate_user(target)
    logger.debug(f"Admin {user_id} approved {target}")
    await message.reply(f"Approved <code>{target}</code>.")


@router.message(Command("disapprove"))
@ensure_user_access(admin_only=True)
async def cmd_disapprove(message: Message):
    user_id = message.from_user.id
    
    target = _parse_target_id(message)
    if target is None:
        await message.reply(
            "Send <code>/disapprove</code> with a chat id, reply to a user, "
            "or send in a group to disapprove it."
        )
        return
    
    removed = await db.remove_approved_chat(target)
    cache.invalidate_user(target)
    logger.debug(f"Admin {user_id} disapproved {target} (was_approved={removed})")
    if removed:
        await message.reply(f"Disapproved <code>{target}</code>.")
    else:
        await message.reply(f"<code>{target}</code> was not approved.")


@router.message(Command("approveonly"))
@ensure_user_access(admin_only=True)
async def cmd_approveonly(message: Message):
    user_id = message.from_user.id
    
    cache.approve_only_mode = not cache.approve_only_mode
    await db.set_global_setting("approve_only_mode", cache.approve_only_mode)

    state = "enabled" if cache.approve_only_mode else "disabled"
    logger.debug(f"Admin {user_id} toggled approve-only mode: {state}")
    await message.reply(f"Approve-only mode <b>{state}</b>.")


@router.message(Command("clearcache"))
@ensure_user_access(admin_only=True)
async def cmd_clearcache(message: Message):
    user_id = message.from_user.id
    
    await reload_cache()
    logger.debug(f"Admin {user_id} cleared cache")
    await message.reply("Cache cleared and reloaded.")