"""Система рейтинга каналов — отслеживание эффективности источников."""

import logging
from sqlalchemy import select, func
from ..models.job import Job
from ..database import async_session

logger = logging.getLogger(__name__)


async def get_channel_ratings() -> list:
    """Возвращает рейтинг каналов по количеству найденных вакансий."""
    async with async_session() as session:
        stmt = (
            select(
                Job.source,
                func.count(Job.id).label("total_jobs"),
                func.max(Job.created_at).label("last_job_at"),
            )
            .group_by(Job.source)
            .order_by(func.count(Job.id).desc())
        )
        result = await session.execute(stmt)
        rows = result.all()

    ratings = []
    for source, total, last_at in rows:
        if total >= 20:
            status = "🟢"
        elif total >= 5:
            status = "🟡"
        else:
            status = "🔴"

        ratings.append(
            {
                "source": source,
                "total": total,
                "last_at": last_at,
                "status": status,
            }
        )

    return ratings


def format_ratings(ratings: list) -> str:
    """Форматирует рейтинг каналов для отображения."""
    if not ratings:
        return "📊 Нет данных по каналам."

    text = "📊 <b>Рейтинг источников вакансий:</b>\n\n"

    for i, r in enumerate(ratings, 1):
        source = r["source"]
        total = r["total"]
        status = r["status"]

        if source == "hh.ru":
            name = "🏢 hh.ru"
        elif source == "habr.career":
            name = "💻 Habr Career"
        elif source == "kwork.ru":
            name = "🟠 Kwork"
        elif source == "fl.ru":
            name = "🔵 FL.ru"
        elif source == "superjob.ru":
            name = "🟣 SuperJob"
        elif source == "zarplata.ru":
            name = "🟤 Zarplata.ru"
        else:
            name = f"📱 @{source}"

        text += f"{status} <b>{i}. {name}</b> — {total} вакансий\n"

    return text
