from __future__ import annotations

import logging

from bot.config import MAX_CONTEXT_CHARS, MAX_CONTEXT_MESSAGES

logger = logging.getLogger(__name__)

_histories: dict[int, list[dict]] = {}


def _total_chars(history: list[dict]) -> int:
    return sum(len(msg.get("content", "")) for msg in history)


def _remove_oldest_non_system(history: list[dict]):
    for idx, msg in enumerate(history):
        if msg["role"] != "system":
            history.pop(idx)
            return
    if history:
        history.pop(0)


def _trim(chat_id: int):
    history = get_history(chat_id)

    while len(history) > MAX_CONTEXT_MESSAGES:
        _remove_oldest_non_system(history)

    while _total_chars(history) > MAX_CONTEXT_CHARS and len(history) > 1:
        _remove_oldest_non_system(history)


def get_history(chat_id: int) -> list[dict]:
    return _histories.setdefault(chat_id, [])


def add_message(chat_id: int, role: str, content: str):
    history = get_history(chat_id)
    history.append({"role": role, "content": content})
    _trim(chat_id)
    logger.debug(f"chat {chat_id}: added {role} message ({len(content)} chars)")


def inject_reply(chat_id: int, text: str):
    history = get_history(chat_id)

    for msg in history[-10:]:
        if msg["content"] == text:
            return

    context_msg = {"role": "user", "content": f"[Replied-to message]: {text}"}
    if history:
        history.insert(len(history) - 1, context_msg)
    else:
        history.append(context_msg)

    _trim(chat_id)
    logger.debug(f"Injected reply context into chat {chat_id}")


def reset_context(chat_id: int):
    _histories.pop(chat_id, None)
    logger.debug(f"Context reset for chat {chat_id}")