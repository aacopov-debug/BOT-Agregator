"""AI-рекомендации с улучшенным форматированием."""

from aiogram import Router, types
from aiogram.filters import Command
from ...services.job_service import JobService
from ...services.user_service import UserService
from ...database import async_session
from ...utils.ranker import rank_jobs, relevance_emoji
from ...utils.categorizer import get_category_label

router = Router()


@router.message(Command("recommend"))
async def cmd_recommend(message: types.Message):
    """Персональные AI-рекомендации."""
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            telegram_id=message.from_user.id, username=message.from_user.username
        )

        if not user.keywords:
            await message.answer(
                "🤖 <b>Персональные рекомендации</b>\n\n"
                "Для работы AI мне нужен ваш профиль.\n\n"
                "Нажмите ⚙️ <b>Настройки</b> → 🔑 <b>Ключевые слова</b>\n"
                "и укажите интересующие технологии.\n\n"
                "Пример: <code>python, remote, middle</code>",
                parse_mode="HTML",
            )
            return

        job_service = JobService(session)
        all_jobs = await job_service.get_latest_jobs(limit=50)

    if not all_jobs:
        await message.answer("😔 Вакансий пока нет. Подождите, бот собирает данные...")
        return

    ranked = rank_jobs(user.keywords, all_jobs)
    top_jobs = ranked[:10]

    # Красивый заголовок
    name = message.from_user.first_name or "вас"
    response = (
        f"🤖 <b>AI-Рекомендации для {name}</b>\n"
        f"🔑 <code>{user.keywords}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
    )

    for score, job in top_jobs:
        emoji = relevance_emoji(score)
        cat_label = get_category_label(job.category) if job.category else ""
        source = job.source or ""
        if source == "hh.ru":
            src = "🏢"
        elif source == "habr.career":
            src = "💻"
        else:
            src = "📱"

        link_text = f"<a href='{job.link}'>→</a>" if job.link else ""

        response += (
            f"{emoji} <b>{score}/10</b>  {job.title[:60]}\n"
            f"    {cat_label}  {src} {source}  {link_text}\n\n"
        )

    response += (
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔥 8-10 = идеальное совпадение\n"
        "✅ 6-7  = хорошее\n"
        "🟡 4-5  = средне\n"
        "⬜ 0-3  = не ваше"
    )

    await message.answer(response, parse_mode="HTML", disable_web_page_preview=True)
