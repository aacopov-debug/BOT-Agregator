"""Главное меню и приветствие с постоянной клавиатурой."""

from aiogram import Router, types, F
from aiogram.filters import CommandStart, CommandObject, StateFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from ...services.user_service import UserService
from ...services.job_service import JobService
from ...database import async_session
from ...utils.keyboards import MAIN_MENU

router = Router()


@router.message(F.text == "❌ Отмена", StateFilter("*"))
@router.message(CommandStart())
async def cmd_start(
    message: types.Message,
    command: CommandObject = None,
    user_id: int = None,
    state: FSMContext = None,
):
    if state:
        await state.clear()

    referrer_id = None
    if command and command.args and command.args.startswith("ref_"):
        try:
            referrer_id = int(command.args.split("_")[1])
        except ValueError:
            pass

    # Определяем ID пользователя и username
    effective_user_id = user_id or message.from_user.id
    effective_username = message.from_user.username if user_id is None else None

    async with async_session() as session:
        user_service = UserService(session)
        await user_service.get_or_create_user(
            telegram_id=effective_user_id,
            username=effective_username,
            referrer_id=referrer_id,
        )
        # Проверка и обновление ежедневного стрика
        streak_res = await user_service.update_daily_streak(effective_user_id)

        job_service = JobService(session)
        total = await job_service.count_jobs()

    streak_text = ""
    # Показываем стрик, даже если он не обновился только что (например, при повторном /start сегодня)
    if streak_res.get("bonus"):
        streak_text = f"🎁 <b>+1 AI-кредит</b> за ежедневную активность! (Стрик: {streak_res.get('streak', 3)} дн.)\n\n"
    elif streak_res.get("streak", 0) > 0:
        streak_text = f"🔥 Ваш стрик: <b>{streak_res['streak']}</b> дн. (Заходите завтра за бонусом!)\n\n"

    name = message.from_user.first_name or "друг"
    jobs_text = (
        f"📦 В базе: <b>{total}</b> вакансий"
        if total
        else "📦 Скоро появятся вакансии..."
    )

    welcome_text = (
        f"👋 <b>Привет, {name}!</b>\n\n"
        f"{streak_text}"
        "Я — <b>Job Aggregator</b> 🤖\n"
        "Ваш персональный помощник в поиске IT-вакансий с ИИ-аналитикой.\n\n"
        "🔍 Собираю предложения из <b>9 источников</b>: TG, hh.ru, Habr, Kwork, FL.ru, Work-Zilla, SuperJob, Zarplata и Rabota.\n\n"
        f"{jobs_text}\n\n"
        "💡 Используйте меню ниже для навигации или введите <code>/help</code> для списка всех команд."
    )

    await message.answer(welcome_text, parse_mode="HTML", reply_markup=MAIN_MENU)


@router.message(F.text == "⚙️ Настройки", StateFilter("*"))
async def btn_settings(message: types.Message, state: FSMContext = None):
    if state:
        await state.clear()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔊 Выбрать голос озвучки", callback_data="set:voice"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📄 Загрузить резюме", callback_data="menu:resume"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔑 Ключевые слова", callback_data="menu:keywords"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📬 Подписки", callback_data="menu:subscribe"
                ),
                InlineKeyboardButton(
                    text="🚫 Blacklist", callback_data="menu:blacklist"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📄 Экспорт избранного", callback_data="menu:export"
                )
            ],
        ]
    )
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            telegram_id=message.from_user.id, username=message.from_user.username
        )
    kw = user.keywords if user.keywords else "не настроены"
    voice = user.voice or "alloy"
    await message.answer(
        f"⚙️ <b>Настройки</b>\n\n"
        f"📝 Ключевые слова: <code>{kw}</code>\n"
        f"🔊 Голос озвучки: <code>{voice}</code>\n\n"
        f"Выберите:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data == "menu:keywords", StateFilter("*"))
async def menu_keywords(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    from .settings import SettingsState

    await callback.message.answer(
        "🔑 Введите ключевые слова через запятую:\n"
        "<code>python, remote, middle</code>\n\nИли /cancel",
        parse_mode="HTML",
    )
    await state.set_state(SettingsState.waiting_for_keywords)


@router.callback_query(F.data == "menu:subscribe", StateFilter("*"))
async def menu_subscribe(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .extra import cmd_subscribe

    await cmd_subscribe(
        callback.message,
        user_id=callback.from_user.id,
        username=callback.from_user.username,
    )


@router.callback_query(F.data == "menu:export", StateFilter("*"))
async def menu_export(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .extra import cmd_export

    await cmd_export(callback.message, user_id=callback.from_user.id)


@router.callback_query(F.data == "menu:resume", StateFilter("*"))
async def menu_resume(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    from ..ai.resume import ResumeState

    if state:
        await state.clear()
    await callback.message.answer(
        "📄 Отправьте текст резюме или перечислите навыки:", parse_mode="HTML"
    )
    await state.set_state(ResumeState.waiting_for_resume)


@router.callback_query(F.data == "menu:blacklist", StateFilter("*"))
async def menu_blacklist(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .blacklist import send_blacklist_menu

    await send_blacklist_menu(callback.message)


@router.message(Command("terms"))
async def cmd_terms(message: types.Message):
    """Пользовательское соглашение."""
    text = (
        "⚖️ <b>Пользовательское соглашение</b>\n\n"
        "1. <b>Общие положения</b>: Бот является агрегатором вакансий из открытых источников.\n"
        "2. <b>Использование данных</b>: Мы собираем ваш ID и username для обеспечения работы функций.\n"
        "3. <b>Подписки и платежи</b>: Оплата Premium-доступа производится через защищенные шлюзы (YooMoney).\n"
        "4. <b>Отказ от ответственности</b>: Мы не несем ответственности за содержание вакансий на сторонних ресурсах.\n\n"
        "Используя бот, вы соглашаетесь с данными условиями."
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("privacy"))
async def cmd_privacy(message: types.Message):
    """Политика конфиденциальности."""
    text = (
        "🛡 <b>Политика конфиденциальности</b>\n\n"
        "• <b>Данные</b>: Мы храним ваш Telegram ID, имя пользователя и загруженное резюме.\n"
        "• <b>Цель</b>: Отображение персональной статистики и подбор вакансий через AI.\n"
        "• <b>Защита</b>: Ваши данные не передаются третьим лицам.\n"
        "• <b>Удаление</b>: Вы можете запросить удаление данных через техподдержку.\n\n"
        "Мы заботимся о вашей приватности."
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("support"))
@router.message(F.text == "🆘 Поддержка")
async def cmd_support(message: types.Message):
    """Контакты поддержки."""
    text = (
        "🆘 <b>Центр поддержки пользователей</b>\n\n"
        "Если у вас возникли вопросы по работе бота, оплате Premium или вы хотите предложить идею:\n\n"
        "👤 <b>Администратор:</b> @Armenacopov\n"
        "🕒 <b>Время ответа:</b> обычно в течение 2-4 часов.\n\n"
        "Перед обращением рекомендуем заглянуть в раздел /help."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💬 Написать админу", url="https://t.me/Armenacopov"
                )
            ],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="menu:start")],
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# === /help ===


@router.message(F.text == "❓ Помощь", StateFilter("*"))
@router.message(lambda m: m.text and m.text.startswith("/help"), StateFilter("*"))
async def cmd_help(message: types.Message, state: FSMContext = None):
    if state:
        await state.clear()
    help_text = (
        "❓ <b>Полный справочник</b>\n\n"
        "━━━ <b>🔎 Поиск вакансий</b> ━━━\n"
        "📋 /jobs — все вакансии (◀️▶️)\n"
        "🔥 /hot — горячие за 24 часа\n"
        "🎲 /random — случайная вакансия\n"
        "🔍 /search — поиск по слову\n"
        "📂 /filter — по категории\n"
        "🌍 /city — по городу\n"
        "💰 /salary_filter — по зарплате\n\n"
        "━━━ <b>🎤 Собеседование & AI</b> ━━━\n"
        "🎤 /interview — AI-тренажер интервью (NEW!)\n"
        "🤖 /recommend — советы ИИ по поиску\n"
        "✉️ Генератор писем (кнопка в описании)\n"
        "📄 /resume — анализ и загрузка резюме\n\n"
        "━━━ <b>💎 Монетизация & Бонусы</b> ━━━\n"
        "💳 /balance — баланс, Карта РФ или ⭐ Stars\n"
        "👑 /premium — тарифы и преимущества\n"
        "🎁 /referral — пригласить друзей (+Premium)\n"
        "🔥 <b>Стрики:</b> заходи 3 дня подряд — получи AI-кредит!\n\n"
        "━━━ <b>🏢 Для работодателей</b> ━━━\n"
        "🏢 /hr — разместить свою вакансию\n"
        "🚀 <b>Продвижение (Карта/Stars):</b> выделитесь в ТОП-е!\n\n"
        "━━━ <b>📊 Аналитика & Профиль</b> ━━━\n"
        "👤 /profile — статистика и настройки\n"
        "📩 /applications — трекер откликов\n"
        "⭐ /favorites — избранное\n"
        "📈 /trends — аналитика рынка\n"
        "🔔 /subs — умные подписки\n\n"
        "━━━ <b>🛠 Настройки</b> ━━━\n"
        "⚙️ /settings — ключевые слова\n"
        "🚫 /blacklist — скрыть компании\n"
        "📄 /export — экспорт в Excel\n"
        "🔐 /admin — тех. поддержка\n\n"
        "<b>9 источников:</b> TG • hh.ru • Habr •\n"
        "Kwork • FL.ru • Work-Zilla • SuperJob • Zarplata • Rabota"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Разделы поиска", callback_data="hub:discovery"
                ),
                InlineKeyboardButton(
                    text="👤 Мой Кабинет", callback_data="hub:cabinet"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="⚙️ Настройки", callback_data="menu:settings_btn"
                ),
                InlineKeyboardButton(
                    text="🆘 Поддержка", url="https://t.me/Armenacopov"
                ),
            ],
        ]
    )
    await message.answer(help_text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "menu:jobs", StateFilter("*"))
async def cb_help_jobs(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from ..discovery.jobs import cmd_jobs

    await cmd_jobs(callback.message)


@router.callback_query(F.data == "menu:settings_btn", StateFilter("*"))
async def cb_help_settings(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await btn_settings(callback.message, state=state)


@router.callback_query(F.data.in_({"menu:main", "menu:start"}), StateFilter("*"))
async def cb_global_menu(callback: types.CallbackQuery, state: FSMContext):
    """Глобальный обработчик возврата в главное меню."""
    await callback.answer()
    if state:
        await state.clear()
    await cmd_start(callback.message, user_id=callback.from_user.id)
