from __future__ import annotations

from datetime import datetime, timezone

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.services.access import is_admin
from bot.services.ai import get_default_model, get_models, model_id_to_alias
from bot.services.time import format_remaining_time, format_utc_dt


def build_settings_message() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "<b>Settings - Trinity AI</b>\n\n"
        "Choose an option below:"
    )
    buttons = [
        [
            InlineKeyboardButton(text="Models", callback_data="settings:models"),
            InlineKeyboardButton(text="Usage", callback_data="settings:usage")
        ],
        [InlineKeyboardButton(text="Streaming", callback_data="settings:streaming")]
    ]
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def build_models_message(current_model_id: str) -> tuple[str, InlineKeyboardMarkup]:
    models = get_models()
    current_model_id = current_model_id or get_default_model()

    selected_name = next(
        (m["name"] for m in models if m["id"] == current_model_id),
        current_model_id
    )

    text = (
        "<b>Choose your AI model:</b>\n\n"
        f"Selected: <code>{selected_name}</code>"
    )
    buttons = [
        [InlineKeyboardButton(text=m["name"], callback_data=f"model:{model_id_to_alias(m['id'])}")]
        for m in models
    ]
    buttons.append([InlineKeyboardButton(text="Go Back", callback_data="settings:back")])

    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


def build_usage_message(user_id: int, counts: dict | None) -> tuple[str, InlineKeyboardMarkup]:
    lines = ["<b>Your Usage - Trinity AI</b>\n"]
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Refresh", callback_data="settings:usage_refresh"),
                InlineKeyboardButton(text="Go Back", callback_data="settings:back")
            ]
        ]
    )

    if is_admin(user_id):
        lines.append("As an admin, you have no rate limits.")
        return "\n".join(lines), markup
    
    if not counts:
        lines.append("No rate limits are currently set for you. Enjoy!")
        return "\n".join(lines), markup

    now = datetime.now(timezone.utc)
    for _, info in counts.items():
        label = info["label"]
        count = info.get("count", 0)
        max_req = info.get("max", "Unlimited")
        reset_at = info.get("reset_at")
        if reset_at and reset_at > now:
            remaining = (reset_at - now).total_seconds()
            time_left = format_remaining_time(remaining)
            lines.append(f"• <b>{label}:</b> {count}/{max_req} (resets in {time_left})")
        else:
            lines.append(f"• <b>{label}:</b> {count}/{max_req}")

    return "\n".join(lines), markup


def build_streaming_message(user_pref: bool) -> str:
    text = (
        "<b>Streaming Messages - Trinity AI</b>\n\n"
        "Streaming Messages is a new feature introduced by Telegram, designed for bots "
        "like Trinity. It allows bots to stream text as it's generated with an animated "
        "effect. Since this is new, some users may find it uncomfortable or use apps "
        "that don't support it, so it's disabled by default.\n\n"
    )
    text += (f"<b>Status:</b> <code>{"Enabled" if user_pref else "Disabled"}</code>\n\n")
    text += (
        "<b>Note:</b>\n"
        "• Only enable this if you have <b>Telegram v12.5.2</b> or newer.\n"
        "• Using it on older Telegram versions will result in a worse experience.\n"
        "• This feature only works in private 1-to-1 chats with Trinity AI."
    )

    toggle_label = "Disable" if user_pref else "Enable"
    buttons = [
        [InlineKeyboardButton(text=toggle_label, callback_data="settings:streaming_toggle")],
        [InlineKeyboardButton(text="Go Back", callback_data="settings:back")]
    ]

    return text, InlineKeyboardMarkup(inline_keyboard=buttons)
