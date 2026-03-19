import logging
from openai import AsyncOpenAI
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from aiogram import Bot

from ..models.job import Job
from ..models.user import User
from ..database import async_session
from ..config import settings
from typing import List
from ..services.job_service import JobService
from ..services.ai_base import BaseAIService

logger = logging.getLogger(__name__)

# Инициализируем клиент OpenAI
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def send_ai_digest(bot: Bot):
    """Утренний AI-дайджест: топ-5 вакансий под профиль каждого пользователя."""
    if not settings.OPENAI_API_KEY:
        logger.info("AI Digest: OPENAI_API_KEY не задан, пропускаем")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    async with async_session() as session:
        # Проверяем, есть ли новые вакансии
        new_count = (
            await session.execute(
                select(func.count(Job.id)).where(Job.created_at >= cutoff)
            )
        ).scalar_one()

        if new_count == 0:
            return

        # Получаем все вакансии за 24 часа
        jobs = (
            (
                await session.execute(
                    select(Job)
                    .where(Job.created_at >= cutoff)
                    .order_by(Job.created_at.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )

        users = (await session.execute(select(User))).scalars().all()

        job_service = JobService(session)

        for db_user in users:
            if not db_user.keywords:
                continue

            # Берем свежие вакансии за 24 часа по ключевым словам
            jobs = await job_service.search_jobs(db_user.keywords, limit=10)
            if not jobs:
                continue

            summary = await _generate_ai_summary(db_user, jobs)

            if summary:
                try:
                    await bot.send_message(
                        db_user.telegram_id,
                        f"✨ <b>Ваш утренний AI-дайджест (Gemini Pro)</b>\n\n{summary}",
                        parse_mode="HTML",
                    )
                except Exception as e:
                    logger.error(f"Failed to send digest to {db_user.telegram_id}: {e}")


async def _generate_ai_summary(user: User, jobs: List[Job]) -> str:
    """Суммаризирует список вакансий под профиль пользователя."""
    ai = BaseAIService()

    jobs_text = ""
    for i, j in enumerate(jobs, 1):
        jobs_text += f"{i}. {j.title} ({j.source}). Ссылка: {j.link}\n"

    prompt = (
        f"Ты — персональный карьерный ассистент. Проанализируй список вакансий для пользователя "
        f"с интересами: '{user.keywords}'.\n\n"
        f"Список вакансий:\n{jobs_text}\n\n"
        f"Задачи:\n"
        f"1. Выбери ТОП-3 самых подходящих вакансии.\n"
        f"2. Для каждой кратко (одной фразой) напиши, почему она подходит.\n"
        f"3. Оформи результат в красивом стиле с использованием эмодзи.\n"
        f"4. Ссылки на вакансии ОБЯЗАТЕЛЬНО сохрани в формате [Название](ссылка).\n"
        f"5. Будь краток и профессионален."
    )

    messages = [
        {
            "role": "system",
            "content": "Ты помогаешь пользователям быстро находить лучшую работу.",
        },
        {"role": "user", "content": prompt},
    ]

    return await ai.get_chat_completion(messages, max_tokens=1500)
