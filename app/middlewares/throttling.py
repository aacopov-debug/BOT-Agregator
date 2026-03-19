import logging
from typing import Any, Awaitable, Callable, Dict
import asyncio
from aiogram import BaseMiddleware
from aiogram.types import Message
from cachetools import TTLCache

try:
    import redis.asyncio as redis

    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False

from ..config import settings

log = logging.getLogger(__name__)

# Fallback in-memory cache
ttlc = TTLCache(maxsize=10_000, ttl=2)


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: int = 2):
        self.rate_limit = rate_limit
        self.redis = None
        if HAS_REDIS and settings.REDIS_URL:
            try:
                self.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            except Exception as e:
                log.warning(f"Throttling Redis init failed: {e}")

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any],
    ) -> Any:
        # Применяем только к обычным юзерам (не инлайн-кнопкам)
        if not getattr(event, "from_user", None):
            return await handler(event, data)

        user_id = event.from_user.id

        if self.redis:
            key = f"throttle_{user_id}"
            try:
                # Быстрый таймаут: 0.1 секунды
                async with asyncio.timeout(0.1):
                    is_throttled = await self.redis.get(key)
                    if is_throttled:
                        return
                    await self.redis.set(key, "1", ex=self.rate_limit)
            except Exception as e:
                log.warning(f"Redis throttling failed, disabling Redis: {e}")
                self.redis = (
                    None  # Отключаем Redis навсегда, чтобы не тормозить будущие запросы
                )
                if user_id in ttlc:
                    return
                ttlc[user_id] = True
        else:
            if user_id in ttlc:
                return
            ttlc[user_id] = True

        return await handler(event, data)
