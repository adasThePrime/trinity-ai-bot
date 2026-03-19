from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, TYPE_CHECKING

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

if TYPE_CHECKING:
    from bot.services.cache import AppCache, UserCache

from bot.config import (
    MONGO_DB_NAME,
    MONGO_URI,
    RATE_LIMITS_APPROVED_USER,
    RATE_LIMITS_DB_THRESHOLD,
    RATE_LIMITS_USER
)

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, uri: str = MONGO_URI, db_name: str = MONGO_DB_NAME):
        self._uri = uri
        self._db_name = db_name
        self._client: AsyncMongoClient | None = None
        self._db: AsyncDatabase = None
        self.__cache: AppCache = None

    @property
    def _cache(self) -> AppCache:
        if self.__cache is None:
            from bot.services.cache import cache
            self.__cache = cache
        return self.__cache

    async def connect(self):
        self._client = AsyncMongoClient(self._uri)
        self._db = self._client[self._db_name]

        await self._db.approved_chats.create_index("chat_id", unique=True)
        await self._db.user_models.create_index("user_id", unique=True)

        logger.info(f"MongoDB connected to {self._db_name}")

    async def close(self):
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("MongoDB connection closed")

    @property
    def _col(self):
        if self._db is None:
            raise RuntimeError("Database not initialised — call connect() first")
        return self._db
    
    async def add_approved_chat(self, chat_id: int) -> bool:
        result = await self._col.approved_chats.update_one(
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id, "approved_at": datetime.now(timezone.utc)}},
            upsert=True
        )
        return result.upserted_id is not None or result.modified_count > 0
    
    async def remove_approved_chat(self, chat_id: int) -> bool:
        result = await self._col.approved_chats.delete_one({"chat_id": chat_id})
        return result.deleted_count > 0
    
    async def is_chat_approved(self, chat_id: int) -> bool:
        doc = await self._col.approved_chats.find_one({"chat_id": chat_id})
        return doc is not None
    
    async def get_all_approved_chats(self) -> list[int]:
        docs = await self._col.approved_chats.find({}, {"chat_id": 1}).to_list()
        return [d["chat_id"] for d in docs]
    
    async def get_global_setting(self, key: str) -> Any:
        doc = await self._col.settings.find_one({"key": key})
        return doc["value"] if doc else None
    
    async def set_global_setting(self, key: str, value):
        await self._col.settings.update_one(
            {"key": key},
            {"$set": {"key": key, "value": value}},
            upsert=True
        )
        logger.debug(f"Global setting '{key}' set to {value}")
    
    async def _ensure_user_settings_cached(self, user_id: int) -> UserCache:
        entry = self._cache.ensure_user(user_id)
        if entry._settings_loaded:
            return entry
        
        doc = await self._col.user_settings.find_one({"user_id": user_id})
        if doc:
            entry.selected_model = doc.get("model_id")
            entry.streaming_enabled = doc.get("streaming_enabled", False)
        else:
            entry.selected_model = None
            entry.streaming_enabled = False
        entry._settings_loaded = True
        return entry

    async def get_user_settings(self, user_id: int) -> dict | None:
        doc = await self._col.user_settings.find_one({"user_id": user_id})
        return doc if doc else None
    
    async def get_user_model(self, user_id: int) -> str | None:
        entry = await self._ensure_user_settings_cached(user_id)
        return entry.selected_model
    
    async def set_user_model(self, user_id: int, model_id: str):
        await self._col.user_settings.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "model_id": model_id}},
            upsert=True
        )
        entry = self._cache.ensure_user(user_id)
        entry.selected_model = model_id
        logger.debug(f"User {user_id} model set to '{model_id}'")
    
    async def get_user_streaming_preference(self, user_id: int) -> bool:
        entry = await self._ensure_user_settings_cached(user_id)
        return entry.streaming_enabled or False

    async def set_user_streaming_preference(self, user_id: int, enabled: bool):
        await self._col.user_settings.update_one(
            {"user_id": user_id},
            {"$set": {"user_id": user_id, "streaming_enabled": enabled}},
            upsert=True
        )
        entry = self._cache.ensure_user(user_id)
        entry.streaming_enabled = enabled
        logger.debug(f"User {user_id} streaming set to {enabled}")

    async def increment_rate_counter(
        self,
        user_id: int,
        window_key: str,
        window_seconds: int
    ):
        now = datetime.now(timezone.utc)
        reset_at = now + timedelta(seconds=window_seconds)

        result = await self._col.rate_limits.update_one(
            {"user_id": user_id, f"{window_key}.reset_at": {"$gt": now}},
            {"$inc": {f"{window_key}.count": 1}}
        )

        if result.matched_count == 0:
            await self._col.rate_limits.update_one(
                {"user_id": user_id},
                {"$set": {window_key: {"count": 1, "reset_at": reset_at}}},
                upsert=True
            )
    
    async def get_rate_count(self, user_id: int, window_key: str) -> int:
        now = datetime.now(timezone.utc)
        doc = await self._col.rate_limits.find_one(
            {"user_id": user_id, f"{window_key}.reset_at": {"$gt": now}},
            {f"{window_key}.count": 1}
        )
        if doc and window_key in doc:
            return doc[window_key]["count"]
        return 0
    
    async def get_usage_stats(self, user_id: int, is_approved: bool = False) -> dict:
        now = datetime.now(timezone.utc)
        doc = await self._col.rate_limits.find_one({"user_id": user_id})

        if is_approved and RATE_LIMITS_APPROVED_USER is not None:
            limits = RATE_LIMITS_APPROVED_USER
        else:
            limits = RATE_LIMITS_USER
        result = {}

        for key, rule in limits.items():
            window = rule["window"]
            if window < RATE_LIMITS_DB_THRESHOLD:
                continue
            max_req = rule["max"]

            count = 0
            reset_at = None

            if doc and key in doc:
                info = doc[key]
                stored_reset = info.get("reset_at")
                if stored_reset and stored_reset.tzinfo is None:
                    stored_reset = stored_reset.replace(tzinfo=timezone.utc)
                if stored_reset and stored_reset > now:
                    count = info.get("count", 0)
                    reset_at = stored_reset

            result[key] = {"label": rule["label"], "count": count, "max": max_req, "reset_at": reset_at}

        return result
    
    async def touch_user(self, user_id: int):
        now = datetime.now(timezone.utc)
        await self._col.users.update_one(
            {"user_id": user_id},
            {
                "$set": {"last_active": now},
                "$setOnInsert": {"first_seen": now, "user_id": user_id}
            },
            upsert=True
        )


db = Database()