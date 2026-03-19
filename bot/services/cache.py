from __future__ import annotations

import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from bot.config import CACHE_MAX_USERS
from bot.services.db import db

logger = logging.getLogger(__name__)

_USER_TOUCH_DEBOUNCE = 300


@dataclass
class UserCache:
    is_approved: bool | None = None
    selected_model: str | None = None
    streaming_enabled: bool | None = None
    _settings_loaded: bool = False
    last_touched: float | None = None
    rate_buckets: dict[str, list[float]] = field(default_factory=dict)
    cooldowns: dict[str, float] = field(default_factory=dict)


class AppCache:
    def __init__(self, max_users: int = CACHE_MAX_USERS):
        self._max_users = max_users
        self._users: OrderedDict[int, UserCache] = OrderedDict()
        self.approve_only_mode: bool = False
    
    def get_user(self, user_id: int) -> UserCache | None:
        entry = self._users.get(user_id)
        if entry is not None:
            self._users.move_to_end(user_id)
        return entry
    
    def set_user(self, user_id: int, data: UserCache):
        if user_id in self._users:
            self._users.move_to_end(user_id)
        self._users[user_id] = data
        while len(self._users) > self._max_users:
            evicted_id, _ = self._users.popitem(last=False)
            logger.debug(f"Cache evicted user {evicted_id}")

    def ensure_user(self, user_id: int) -> UserCache:
        entry = self.get_user(user_id)
        if entry is None:
            entry = UserCache()
            self.set_user(user_id, entry)
        return entry
    
    def invalidate_user(self, user_id: int):
        self._users.pop(user_id, None)

    def invalidate_all(self):
        self._users.clear()
        logger.debug("Users cache completely nuked")

    def should_touch(self, user_id: int) -> bool:
        entry = self.get_user(user_id)
        if entry is None or entry.last_touched is None:
            return True
        return (time.monotonic() - entry.last_touched) >= _USER_TOUCH_DEBOUNCE
    
    def mark_touched(self, user_id: int):
        entry = self.ensure_user(user_id)
        entry.last_touched = time.monotonic()


cache = AppCache()


async def load_startup_data():
    val = await db.get_global_setting("approve_only_mode")
    cache.approve_only_mode = bool(val) if val is not None else False
    logger.debug(f"Cache loaded: approve_only_mode={cache.approve_only_mode}")


async def reload_cache():
    cache.invalidate_all()
    await load_startup_data()
    logger.debug("Cache reloaded")