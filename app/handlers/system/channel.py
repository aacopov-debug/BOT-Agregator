"""Обработка постов каналов, где бот — администратор."""

import logging
from aiogram import Router, types
from ...services.job_service import JobService
from ...database import async_session
from ...utils.categorizer import detect_category

logger = logging.getLogger(__name__)
router = Router()

# Ключевые слова для фильтрации вакансий
JOB_KEYWORDS = [
    "вакансия",
    "job",
    "hiring",
    "ищем",
    "remote",
    "удаленка",
    "работа",
    "требуется",
    "оклад",
    "зарплата",
    "developer",
    "разработчик",
    "менеджер",
    "junior",
    "middle",
    "senior",
]


@router.channel_post()
async def handle_channel_post(message: types.Message):
    """Автоматически обрабатывает новые посты из каналов, где бот — админ."""
    if not message.text:
        return

    text_lower = message.text.lower()

    # Проверяем, похоже ли сообщение на вакансию
    if not any(kw in text_lower for kw in JOB_KEYWORDS):
        return

    lines = message.text.split("\n")
    title = lines[0][:255] if lines else "Без названия"
    description = message.text[:2000]

    # Формируем ссылку на пост
    chat = message.chat
    channel_username = chat.username or str(chat.id)
    link = (
        f"https://t.me/{channel_username}/{message.message_id}" if chat.username else ""
    )

    # Автокатегоризация
    category = detect_category(title, description)

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.add_job(
            title=title,
            description=description,
            link=link,
            source=channel_username,
            category=category,
        )
        if job:
            logger.info(
                f"✅ New job from @{channel_username}: {job.title} [{category}]"
            )
