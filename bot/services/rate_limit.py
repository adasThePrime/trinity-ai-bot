from __future__ import annotations

from functools import wraps
import logging
import time

from aiogram.types import ChosenInlineResult, Message

from bot.config import RATE_LIMITS_APPROVED_USER, RATE_LIMITS_DB_THRESHOLD, RATE_LIMITS_USER
from bot.services.access import is_admin, is_user_approved
from bot.services.cache import cache
from bot.services.db import db
from bot.services.time import format_remaining_time
from bot.utils.auth import get_user_id

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(
        self,
        limits_users: dict[str, dict] = RATE_LIMITS_USER,
        limits_approved_users: dict[str, dict] | None = RATE_LIMITS_APPROVED_USER
    ):
        self._limits_users = limits_users
        self._limits_approved_users = limits_approved_users

        self._db_windows: dict[str, int] = {}
        for src in (limits_users, limits_approved_users or {}):
            for key, rule in src.items():
                if rule["window"] >= RATE_LIMITS_DB_THRESHOLD:
                    self._db_windows[key] = max(
                        self._db_windows.get(key, 0), rule["window"]
                    )

    def _get_limits(self, is_approved: bool) -> dict[str, dict]:
        if is_approved and self._limits_approved_users is not None:
            return self._limits_approved_users
        return self._limits_users
    
    async def check(self, user_id: int, is_approved: bool) -> tuple[bool, str | None]:
        limits = self._get_limits(is_approved)
        if not limits:
            return True, None
        
        now = time.monotonic()
        user = cache.ensure_user(user_id)

        for key, cooldown_until in user.cooldowns.items():
            if now < cooldown_until:
                remaining = cooldown_until - now
                return False, format_remaining_time(remaining)
            
        for key, rule in limits.items():
            max_req = rule["max"]
            window = rule["window"]
            cooldown = rule.get("cooldown", window)

            if window >= RATE_LIMITS_DB_THRESHOLD:
                count = await db.get_rate_count(user_id, key)
                if count >= max_req:
                    user.cooldowns[key] = now + cooldown
                    return False, format_remaining_time(cooldown)
            else:
                bucket = user.rate_buckets.setdefault(key, [])
                cutoff = now - window
                bucket[:] = [t for t in bucket if t > cutoff]
                if len(bucket) >= max_req:
                    oldest_relevant = bucket[0]
                    natural_wait = (oldest_relevant + window) - now
                    wait = max(natural_wait, cooldown) if cooldown != window else natural_wait
                    user.cooldowns[key] = now + wait
                    return False, format_remaining_time(wait)
            
        return True, None
    
    async def record(self, user_id: int):
        now = time.monotonic()
        user = cache.ensure_user(user_id)

        for key in list(user.rate_buckets):
            user.rate_buckets[key].append(now)
        
        for key, seconds in self._db_windows.items():
            await db.increment_rate_counter(user_id, key, seconds)


rate_limiter = RateLimiter()


async def _deny_rate_limit(event: ChosenInlineResult | Message, time_remaining: str):
    text = f"<b>You're currently rate-limited!</b> Please try again in {time_remaining}"
    if isinstance(event, Message):
        await event.reply(text)
    if isinstance(event, ChosenInlineResult) and event.inline_message_id:
        await event.bot.edit_message_text(
            text=text,
            inline_message_id=event.inline_message_id,
            reply_markup=None
        )


def enforce_rate_limit():
    def decorator(handler):
        @wraps(handler)
        async def wrapper(
            event: ChosenInlineResult | Message, *args, **kwargs
        ):
            user_id = get_user_id(event)
            if is_admin(user_id):
                return await handler(event, *args, **kwargs)
            approved = await is_user_approved(user_id)
            allowed, time_remaining = await rate_limiter.check(user_id, approved)
            if not allowed:
                logger.debug(f"User {user_id} rate-limited, remaining: {time_remaining}")
                await _deny_rate_limit(event, time_remaining)
                return
            await rate_limiter.record(user_id)
            return await handler(event, *args, **kwargs)
        
        return wrapper
    
    return decorator
