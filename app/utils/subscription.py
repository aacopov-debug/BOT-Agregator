import logging
from aiogram import Bot

logger = logging.getLogger(__name__)

# Простой кэш: {user_id: (is_subscribed, timestamp)}
_sub_cache = {}
CACHE_TTL = 300  # 5 минут


async def is_subscribed(bot: Bot, user_id: int, channel_id: str | int) -> bool:
    """
    Проверяет, подписан ли пользователь на указанный канал (с кэшированием).
    """
    if not channel_id:
        return True

    import time

    now = time.time()

    # Проверяем кэш
    if user_id in _sub_cache:
        cached_sub, timestamp = _sub_cache[user_id]
        if now - timestamp < CACHE_TTL:
            return cached_sub

    try:
        member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
        # Статусы, говорящие о подписке: member, administrator, creator
        is_sub = member.status in ["member", "administrator", "creator"]

        # Обновляем кэш
        _sub_cache[user_id] = (is_sub, now)
        return is_sub
    except Exception as e:
        logger.warning(
            f"Error checking subscription for user {user_id} in {channel_id}: {e}"
        )
        return True
