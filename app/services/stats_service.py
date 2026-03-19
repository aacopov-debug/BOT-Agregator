import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.stats import ParserStats
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


class StatsService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def update_parser_stats(
        self, name: str, found: int, status: str = "OK", error: str = None
    ):
        """Обновляет или создает запись статистики для парсера."""
        try:
            # Ищем существующую запись
            stmt = select(ParserStats).where(ParserStats.parser_name == name)
            result = await self.session.execute(stmt)
            stats = result.scalar_one_or_none()

            now = datetime.now(timezone.utc)

            if not stats:
                stats = ParserStats(
                    parser_name=name,
                    vacancies_found=found,
                    total_today=found,
                    status=status,
                    last_error=error,
                    updated_at=now,
                )
                self.session.add(stats)
            else:
                # Сброс дневной статистики, если последнее обновление было вчера
                # (Упрощенно: если прошло более 24 часов с updated_at)
                if stats.updated_at and now - stats.updated_at.replace(
                    tzinfo=timezone.utc
                ) > timedelta(days=1):
                    stats.total_today = found
                else:
                    stats.total_today += found

                stats.vacancies_found = found
                stats.status = status
                stats.last_error = error
                stats.updated_at = now

            await self.session.commit()
        except Exception as e:
            logger.error(f"Error updating parser stats: {e}")
            await self.session.rollback()

    async def get_all_stats(self):
        """Возвращает список всех статистик."""
        stmt = select(ParserStats).order_by(ParserStats.parser_name)
        result = await self.session.execute(stmt)
        return result.scalars().all()
