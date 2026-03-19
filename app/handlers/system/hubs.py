from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from ...utils.keyboards import get_main_menu_button

router = Router()


@router.callback_query(F.data == "hub:cabinet", StateFilter("*"))
async def cb_hub_cabinet(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await hub_cabinet(callback.message, state=state)


@router.callback_query(F.data == "hub:discovery", StateFilter("*"))
async def cb_hub_discovery(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await hub_discovery(callback.message, state=state)


@router.message(F.text == "🔍 Поиск и Вакансии", StateFilter("*"))
async def hub_discovery(message: types.Message, state: FSMContext = None):
    """Хаб поиска и исследования вакансий."""
    if state:
        await state.clear()
    text = (
        "🔍 <b>Поиск и Вакансии</b>\n\n"
        "Здесь вы можете найти работу мечты, используя фильтры и умный поиск."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Все вакансии", callback_data="jobs_page:0"
                ),
                InlineKeyboardButton(text="🔥 Горячие (24ч)", callback_data="hub:hot"),
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Текстовый поиск", callback_data="hub:search"
                ),
                InlineKeyboardButton(text="📂 Категории", callback_data="hub:filter"),
            ],
            [
                InlineKeyboardButton(text="🌍 По городам", callback_data="hub:city"),
                InlineKeyboardButton(text="💰 По зарплате", callback_data="hub:salary"),
            ],
            [
                InlineKeyboardButton(text="🎲 Случайная", callback_data="hub:random"),
                InlineKeyboardButton(
                    text="📬 Подписки", callback_data="menu:subscribe"
                ),
            ],
            [get_main_menu_button()],
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(F.text == "👤 Мой Кабинет", StateFilter("*"))
async def hub_cabinet(message: types.Message, state: FSMContext = None):
    """Хаб личного кабинета пользователя."""
    if state:
        await state.clear()
    text = (
        "👤 <b>Мой Кабинет</b>\n\n"
        "Управляйте своим профилем, откликами и избранными вакансиями."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Мой Профиль", callback_data="profile:main"
                ),
                InlineKeyboardButton(
                    text="⭐ Избранное", callback_data="hub:favorites"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📩 Трекер откликов", callback_data="tracker:list"
                ),
                InlineKeyboardButton(text="📄 Мое Резюме", callback_data="menu:resume"),
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Достижения", callback_data="profile:achievements"
                ),
                InlineKeyboardButton(text="🎁 Рефералы", callback_data="menu:referral"),
            ],
            [get_main_menu_button()],
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.message(F.text == "📊 Аналитика", StateFilter("*"))
async def hub_analytics(message: types.Message, state: FSMContext = None):
    """Хаб аналитики рынка."""
    if state:
        await state.clear()
    from .analytics import cmd_analytics_hub

    await cmd_analytics_hub(message)


@router.callback_query(F.data == "hub:analytics", StateFilter("*"))
async def cb_hub_analytics(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .analytics import cmd_analytics_hub

    await cmd_analytics_hub(callback.message)


@router.message(F.text == "🤖 AI Помощник", StateFilter("*"))
async def hub_ai(message: types.Message, state: FSMContext = None):
    """Хаб AI-инструментов."""
    if state:
        await state.clear()
    text = (
        "🤖 <b>AI Помощник</b>\n\n"
        "Используйте мощь нейросетей для ускорения поиска работы."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎤 AI-Интервью", callback_data="hub:interview"
                ),
                InlineKeyboardButton(
                    text="🤖 Рекомендации", callback_data="hub:recommend"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎯 Matching (Резюме)", callback_data="resume:match"
                ),
                InlineKeyboardButton(
                    text="✍️ Генератор писем", callback_data="hub:cover"
                ),
            ],
            [get_main_menu_button()],
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# === Discovery Hub Callbacks ===


@router.callback_query(F.data == "hub:hot", StateFilter("*"))
async def cb_hub_hot(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from ..cabinet.profile import cmd_hot

    await cmd_hot(callback.message)


@router.callback_query(F.data == "hub:search", StateFilter("*"))
async def cb_hub_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    from ..discovery.search import cmd_search

    await cmd_search(callback.message, state)


@router.callback_query(F.data == "hub:filter", StateFilter("*"))
async def cb_hub_filter(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from ..discovery.search import cmd_filter

    await cmd_filter(callback.message)


@router.callback_query(F.data == "hub:city", StateFilter("*"))
async def cb_hub_city(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from ..discovery.city_compare import cmd_city

    await cmd_city(callback.message)


@router.callback_query(F.data == "hub:random", StateFilter("*"))
async def cb_hub_random(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .utils import cmd_random

    await cmd_random(callback.message)


@router.callback_query(F.data == "hub:salary", StateFilter("*"))
async def cb_hub_salary(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .analytics import cmd_salary_analytics

    await cmd_salary_analytics(callback.message)


@router.callback_query(F.data == "hub:favorites", StateFilter("*"))
async def cb_hub_favorites(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from ..cabinet.favorites import cmd_favorites

    await cmd_favorites(callback.message)


@router.callback_query(F.data == "menu:subscribe", StateFilter("*"))
async def cb_hub_subscribe(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .extra import cmd_subscribe

    await cmd_subscribe(callback.message)


# === Cabinet Hub Callbacks ===


@router.callback_query(F.data == "menu:resume", StateFilter("*"))
async def cb_hub_resume(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    from ..ai.resume import cmd_resume

    await cmd_resume(callback.message, state)


# === AI Hub Callbacks ===


@router.callback_query(F.data == "hub:interview", StateFilter("*"))
async def cb_hub_interview(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    from ..ai.interview import cmd_interview

    await cmd_interview(callback.message, state)


@router.callback_query(F.data == "hub:recommend", StateFilter("*"))
async def cb_hub_recommend(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from ..ai.recommend import cmd_recommend

    await cmd_recommend(callback.message)


@router.callback_query(F.data == "hub:cover", StateFilter("*"))
async def cb_hub_cover(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    await callback.message.answer(
        "Выберите вакансию для генерации письма в разделе Поиск."
    )


# === Global Callbacks ===


@router.callback_query(F.data == "menu:close", StateFilter("*"))
async def cb_close(callback: types.CallbackQuery, state: FSMContext = None):
    await callback.answer()
    if state:
        await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
