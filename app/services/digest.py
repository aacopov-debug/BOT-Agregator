"""Утренний дайджест и тренды вакансий."""

import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from aiogram import Bot

from ..models.job import Job
from ..models.user import User
from ..database import async_session
from ..utils.categorizer import get_category_label

logger = logging.getLogger(__name__)


async def send_morning_digest(bot: Bot):
    """Утренний дайджест: новые вакансии за последние 24 часа."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    async with async_session() as session:
        # Количество новых за 24ч
        new_count_stmt = select(func.count(Job.id)).where(Job.created_at >= cutoff)
        result = await session.execute(new_count_stmt)
        new_count = result.scalar_one()

        if new_count == 0:
            return

        # Топ категории за 24ч
        cat_stmt = (
            select(Job.category, func.count(Job.id).label("cnt"))
            .where(Job.created_at >= cutoff)
            .group_by(Job.category)
            .order_by(func.count(Job.id).desc())
            .limit(5)
        )
        cat_result = await session.execute(cat_stmt)
        top_cats = cat_result.all()

        # Топ источники за 24ч
        src_stmt = (
            select(Job.source, func.count(Job.id).label("cnt"))
            .where(Job.created_at >= cutoff)
            .group_by(Job.source)
            .order_by(func.count(Job.id).desc())
            .limit(5)
        )
        src_result = await session.execute(src_stmt)
        top_sources = src_result.all()

        # Все пользователи
        users_stmt = select(User)
        users_result = await session.execute(users_stmt)
        users = users_result.scalars().all()

    if not users:
        return

    # Формируем дайджест
    cats_text = ""
    for cat, cnt in top_cats:
        label = get_category_label(cat)
        cats_text += f"  {label}: +{cnt}\n"

    sources_text = ""
    for src, cnt in top_sources:
        if src == "hh.ru":
            name = "🏢 hh.ru"
        elif src == "habr.career":
            name = "💻 Habr"
        else:
            name = f"📱 @{src}"
        sources_text += f"  {name}: +{cnt}\n"

    digest = (
        f"☀️ <b>Доброе утро! Дайджест вакансий</b>\n\n"
        f"📊 За последние 24 часа: <b>+{new_count}</b> новых\n\n"
        f"<b>По категориям:</b>\n{cats_text}\n"
        f"<b>По источникам:</b>\n{sources_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👉 /jobs — посмотреть все\n"
        f"👉 /recommend — AI-подборка для вас"
    )

    sent = 0
    for user in users:
        try:
            await bot.send_message(
                chat_id=user.telegram_id, text=digest, parse_mode="HTML"
            )
            sent += 1
        except Exception:
            pass

    logger.info(f"☀️ Дайджест отправлен {sent} пользователям (+{new_count} вакансий)")


async def get_trends() -> dict:
    """Тренды: изменение количества вакансий за неделю по дням."""
    trends = {}
    async with async_session() as session:
        for days_ago in range(6, -1, -1):
            start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(days=days_ago)
            end = start + timedelta(days=1)
            stmt = select(func.count(Job.id)).where(
                Job.created_at >= start, Job.created_at < end
            )
            result = await session.execute(stmt)
            count = result.scalar_one()
            day_label = start.strftime("%d.%m")
            trends[day_label] = count

    return trends


def format_trends(trends: dict) -> str:
    """Красивый текстовый график трендов."""
    if not trends or all(v == 0 for v in trends.values()):
        return "📈 Пока нет данных для трендов."

    max_val = max(trends.values()) or 1
    text = "📈 <b>Тренды за неделю</b>\n\n"

    for day, count in trends.items():
        bar_len = int((count / max_val) * 12)
        bar = "▓" * bar_len + "░" * (12 - bar_len)
        text += f"<code>{day} {bar} {count}</code>\n"

    return text
