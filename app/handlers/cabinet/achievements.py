"""Геймификация и система достижений."""

from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from ...database import async_session
from ...models.user import User
from ...models.favorite import Favorite
from ...models.application import Application
from ..discovery.market import SearchHistory  # UPDATED RELATIVE PATH

router = Router()


# Список возможных достижений
ACHIEVEMENTS = [
    {
        "id": "first_blood",
        "icon": "💼",
        "title": "Первый шаг",
        "desc": "Сделан первый отклик на вакансию",
        "condition": lambda stats: stats.get("apps", 0) >= 1,
    },
    {
        "id": "hunter",
        "icon": "🔥",
        "title": "Охотник за офферами",
        "desc": "Сделано 10 и более откликов",
        "condition": lambda stats: stats.get("apps", 0) >= 10,
    },
    {
        "id": "collector",
        "icon": "⭐",
        "title": "Коллекционер",
        "desc": "Добавлено 5 вакансий в избранное",
        "condition": lambda stats: stats.get("favs", 0) >= 5,
    },
    {
        "id": "sniper",
        "icon": "🎯",
        "title": "Снайпер",
        "desc": "Добавлено 20 вакансий в избранное",
        "condition": lambda stats: stats.get("favs", 0) >= 20,
    },
    {
        "id": "tuned",
        "icon": "⚙️",
        "title": "Программист бота",
        "desc": "Настроены ключевые слова для поиска",
        "condition": lambda stats: stats.get("keywords") is not None,
    },
    {
        "id": "researcher",
        "icon": "📈",
        "title": "Исследователь",
        "desc": "Сделано 5 поисковых запросов",
        "condition": lambda stats: stats.get("searches", 0) >= 5,
    },
]


@router.message(Command("achievements"))
async def cmd_achievements(message: types.Message, user_id: int = None):
    """Показать достижения пользователя."""
    if user_id is None:
        user_id = message.from_user.id

    async with async_session() as session:
        # Собираем статистику для условий
        apps = (
            await session.execute(
                select(func.count(Application.id)).where(
                    Application.user_telegram_id == user_id
                )
            )
        ).scalar_one()

        favs = (
            await session.execute(
                select(func.count(Favorite.id)).where(
                    Favorite.user_telegram_id == user_id
                )
            )
        ).scalar_one()

        searches = (
            await session.execute(
                select(func.count(SearchHistory.id)).where(
                    SearchHistory.user_telegram_id == user_id
                )
            )
        ).scalar_one()

        user = (
            await session.execute(select(User).where(User.telegram_id == user_id))
        ).scalar_one_or_none()

        stats = {
            "apps": apps,
            "favs": favs,
            "searches": searches,
            "keywords": user.keywords if user and user.keywords else None,
        }

    # Вычисляем ачивки
    earned = []
    locked = []

    for ach in ACHIEVEMENTS:
        if ach["condition"](stats):
            earned.append(ach)
        else:
            locked.append(ach)

    # Формируем ответ
    text = f"🏆 <b>Ваши Достижения</b> ({len(earned)}/{len(ACHIEVEMENTS)})\n\n"

    if earned:
        text += "<b>Полученные:</b>\n"
        for ach in earned:
            text += f"{ach['icon']} <b>{ach['title']}</b>\n   <i>{ach['desc']}</i>\n\n"
    else:
        text += "<i>Вы пока не получили ни одного достижения. Откликнитесь на вакансию или добавьте в избранное!</i>\n\n"

    if locked:
        text += "<b>Доступные для получения:</b>\n"
        for ach in locked:
            text += f"🔒 <b>{ach['title']}</b>\n   <i>{ach['desc']}</i>\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В профиль", callback_data="profile:main")]
        ]
    )

    if hasattr(message, "edit_text"):
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "profile:main", StateFilter("*"))
async def callback_btn_profile(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .profile import cmd_profile

    await cmd_profile(callback.message, user_id=callback.from_user.id, edit=True)
