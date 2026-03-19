import logging
from aiogram import Router, types
from aiogram.filters import Command
from ...config import settings
from ...database import async_session
from ...services.stats_service import StatsService

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Выводит статистику работы парсеров."""
    if message.from_user.id != settings.ADMIN_ID:
        return

    async with async_session() as session:
        stats_service = StatsService(session)
        all_stats = await stats_service.get_all_stats()

    if not all_stats:
        await message.answer(
            "📊 Статистика пока пуста. Подождите первого запуска парсеров."
        )
        return

    text = "🖥 **Мониторинг парсеров**\n"
    text += "━━━━━━━━━━━━\n"

    for s in all_stats:
        status_icon = "🟢" if s.status == "OK" else "🔴"
        if s.status == "BAN":
            status_icon = "🚫"

        text += f"{status_icon} **{s.parser_name}**: {s.vacancies_found} (сегодня: {s.total_today})\n"
        if s.status != "OK" and s.last_error:
            # Обрезаем ошибку для краткости
            err_msg = (
                s.last_error[:50] + "..." if len(s.last_error) > 50 else s.last_error
            )
            text += f"   └ ⚠️ _{err_msg}_\n"

    text += "━━━━━━━━━━━━\n"
    text += f"📅 Последнее обновление: {all_stats[0].updated_at.strftime('%H:%M:%S') if all_stats else '—'}"

    await message.answer(text, parse_mode="Markdown")
