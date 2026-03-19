"""Профиль пользователя, горячие вакансии, расписание уведомлений."""

import re
import html
from datetime import datetime, timedelta, timezone
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from ...services.job_service import JobService
from ...services.user_service import UserService
from ...models.job import Job
from ...models.favorite import Favorite
from ...database import async_session
from ...utils.categorizer import get_category_label
from ...utils.resume_parser import parse_resume

router = Router()


# ===== /profile — Личный кабинет =====


@router.message(Command("profile"))
@router.message(F.text == "👤 Профиль")
async def cmd_profile(message: types.Message, user_id: int = None, edit: bool = False):
    """Личный профиль с аналитикой."""
    if user_id is None:
        user_id = message.from_user.id
        user_name = message.from_user.username
        first_name = message.from_user.first_name
    else:
        # Для случаев вызова из callback
        user_name = None
        first_name = "Пользователь"

    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(user_id, user_name)
        job_service = JobService(session)
        fav_count = await job_service.count_favorites(user_id)
        await job_service.count_jobs()

        # Топ-категории из избранного
        fav_cats_stmt = (
            select(Job.category, func.count(Job.id))
            .join(Favorite, Favorite.job_id == Job.id)
            .where(Favorite.user_telegram_id == user_id)
            .group_by(Job.category)
            .order_by(func.count(Job.id).desc())
            .limit(3)
        )
        fav_cats = (await session.execute(fav_cats_stmt)).all()

    name = first_name or "Пользователь"
    username = f"@{user_name}" if user_name else "—"
    kw = user.keywords if user.keywords else "не настроены"

    # Парсинг навыков из keywords
    profile = parse_resume(kw) if kw != "не настроены" else None
    skills_count = len(profile["skills"]) if profile else 0

    # Уровень активности
    if fav_count >= 20:
        level = "🏆 Эксперт"
    elif fav_count >= 10:
        level = "⭐ Продвинутый"
    elif fav_count >= 3:
        level = "📊 Активный"
    else:
        level = "🆕 Новичок"

    # Режим уведомлений
    notify_labels = {
        "instant": "⚡ Мгновенно",
        "morning": "☀️ Утром (9:00)",
        "off": "🔕 Выключены",
    }
    notify_text = notify_labels.get(user.notify_mode or "instant", "⚡ Мгновенно")

    # Дата регистрации
    reg_date = user.created_at.strftime("%d.%m.%Y") if user.created_at else "—"

    response = (
        f"👤 <b>Профиль: {name}</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"  📛 {username}\n"
        f"  🎯 Уровень: {level}\n"
        f"  📅 С нами с: {reg_date}\n"
        f"  🔔 Уведомления: {notify_text}\n"
        f"  🎙 Голос: <b>{user.voice or 'nova'}</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔑 <b>Ключевые слова:</b>\n<code>{kw[:80]}</code>\n"
        f"🛠 Навыков: {skills_count}\n\n"
        f"⭐ В избранном: <b>{fav_count}</b>\n"
    )

    if fav_cats:
        response += "\n📂 <b>Интересы (по ⭐):</b>\n"
        for cat, cnt in fav_cats:
            label = get_category_label(cat)
            response += f"  {label}: {cnt}\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Ачивки", callback_data="profile:achievements"
                ),
                InlineKeyboardButton(text="🔑 Слова", callback_data="profile:keywords"),
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Уведомления", callback_data="profile:notify"
                ),
                InlineKeyboardButton(text="📄 Резюме", callback_data="resume:reload"),
            ],
            [
                InlineKeyboardButton(text="🎯 Matching", callback_data="resume:match"),
                InlineKeyboardButton(
                    text="🎁 Друзья (+3 ИИ)", callback_data="menu:referral"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="👑 Premium (Карта/Stars)", callback_data="shop:premium"
                ),
                InlineKeyboardButton(text="🎙 Голос", callback_data="profile:voice"),
            ],
            [
                InlineKeyboardButton(
                    text="💳 Баланс / Пополнение", callback_data="back_balance"
                ),
                InlineKeyboardButton(text="🏠 В меню", callback_data="menu:main"),
            ],
        ]
    )

    if edit:
        await message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(response, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data == "profile:keywords", StateFilter("*"))
async def profile_keywords(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    from ..system.settings import SettingsState

    await callback.message.answer(
        "🔑 Введите ключевые слова через запятую:\n"
        "<code>python, react, remote</code>\n\n/cancel",
        parse_mode="HTML",
    )
    await state.set_state(SettingsState.waiting_for_keywords)


@router.callback_query(F.data == "profile:main", StateFilter("*"))
async def profile_main(callback: types.CallbackQuery, state: FSMContext):
    """Возврат в главное меню профиля."""
    await callback.answer()
    if state:
        await state.clear()
    await cmd_profile(callback.message, user_id=callback.from_user.id, edit=True)


@router.callback_query(F.data == "profile:achievements", StateFilter("*"))
async def profile_achievements(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    from .achievements import cmd_achievements

    await cmd_achievements(callback.message, user_id=callback.from_user.id)


# ===== Расписание уведомлений =====


@router.callback_query(F.data == "profile:notify")
async def profile_notify(callback: types.CallbackQuery):
    """Выбор режима уведомлений."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚡ Мгновенно", callback_data="notify_set:instant"
                )
            ],
            [
                InlineKeyboardButton(
                    text="☀️ Утром (9:00)", callback_data="notify_set:morning"
                )
            ],
            [InlineKeyboardButton(text="🔕 Выключить", callback_data="notify_set:off")],
        ]
    )
    await callback.message.edit_text(
        "🔔 <b>Режим уведомлений</b>\n\n"
        "⚡ <b>Мгновенно</b> — сразу при появлении\n"
        "☀️ <b>Утром</b> — дайджест в 9:00\n"
        "🔕 <b>Выкл</b> — без уведомлений",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("notify_set:"))
async def set_notify_mode(callback: types.CallbackQuery):
    mode = callback.data.split(":")[1]
    labels = {"instant": "⚡ Мгновенно", "morning": "☀️ Утром", "off": "🔕 Выключены"}

    async with async_session() as session:
        user_service = UserService(session)
        await user_service.update_notify_mode(callback.from_user.id, mode)

    await callback.message.edit_text(
        f"✅ Режим уведомлений: <b>{labels.get(mode, mode)}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="profile:main")]
            ]
        ),
    )
    await callback.answer()


# ===== Настройка Голоса =====


@router.callback_query(F.data == "profile:voice")
async def profile_voice_menu(callback: types.CallbackQuery):
    """Выбор голоса для TTS."""
    voices = [
        ("Alloy (Нейтральный)", "alloy"),
        ("Echo (Глубокий)", "echo"),
        ("Onyx (Грубый)", "onyx"),
        ("Nova (Ясный/Четкий)", "nova"),
        ("Shimmer (Мягкий)", "shimmer"),
    ]
    premium_voices = [
        ("💎 Bella (Premium)", "eleven_EXAVITQu4vr4xnSDxMaL"),
        ("💎 Adam (Premium)", "eleven_pNInz6obpgDQGcFmaJgB"),
    ]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"voice_set:{code}")]
            for name, code in voices
        ]
        + [
            [InlineKeyboardButton(text=name, callback_data=f"voice_set:{code}")]
            for name, code in premium_voices
        ]
        + [[InlineKeyboardButton(text="◀️ Назад", callback_data="profile:main")]]
    )

    await callback.message.edit_text(
        "🎙 <b>Выбор AI-Голоса</b>\n\n"
        "Выберите голос для озвучки вакансий и отчетов.\n\n"
        "🟢 <b>Стандартные (OpenAI):</b>\n"
        "Быстрые и надежные. Рекомендуем <i>Nova</i>.\n\n"
        "💎 <b>Premium (ElevenLabs):</b>\n"
        "Самые живые и эмоциональные голоса с идеальным произношением.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("voice_set:"))
async def set_voice_mode(callback: types.CallbackQuery):
    voice_code = callback.data.split(":")[1]

    async with async_session() as session:
        user_service = UserService(session)
        # В UserService может не быть метода update_voice, так что обновим напрямую
        user = await user_service.get_or_create_user(callback.from_user.id)
        user.voice = voice_code
        await session.commit()

    await callback.message.edit_text(
        f"✅ Голос изменен на: <b>{voice_code}</b>\n"
        "Теперь вакансии будут озвучиваться этим голосом.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="◀️ Назад", callback_data="profile:main")]
            ]
        ),
    )
    await callback.answer()


# ===== /hot — Горячие вакансии за 24ч =====


@router.message(Command("hot"))
async def cmd_hot(message: types.Message):
    """Горячие вакансии — свежие за последние 24 часа."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    async with async_session() as session:
        stmt = (
            select(Job)
            .where(Job.created_at >= cutoff)
            .order_by(Job.created_at.desc())
            .limit(10)
        )
        result = await session.execute(stmt)
        jobs = result.scalars().all()

        total_stmt = select(func.count(Job.id)).where(Job.created_at >= cutoff)
        total = (await session.execute(total_stmt)).scalar_one()

    if not jobs:
        await message.answer("🔥 За последние 24 часа новых вакансий нет.")
        return

    response = f"🔥 <b>Горячие вакансии</b>  •  +{total} за 24ч\n\n"
    for i, job in enumerate(jobs, 1):
        cat = get_category_label(job.category) if job.category else ""
        src = (
            "🏢"
            if job.source == "hh.ru"
            else ("💻" if job.source == "habr.career" else "📱")
        )

        # Извлекаем зарплату
        salary = _extract_salary_short(f"{job.title} {job.description or ''}")

        # Время
        if job.created_at:
            age = datetime.now(timezone.utc) - job.created_at
            if age.seconds < 3600:
                time_ago = f"{age.seconds // 60}мин"
            else:
                time_ago = f"{age.seconds // 3600}ч"
        else:
            time_ago = ""

        if not job.link:
            continue

        link = f"<a href='{job.link}'>→</a>"

        safe_title = html.escape(job.title[:55])
        response += (
            f"<b>{i}.</b> {cat} {safe_title}\n"
            f"   {src} {salary}  🕐{time_ago}  {link}\n\n"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Все вакансии", callback_data="jobs_page:0"
                ),
                InlineKeyboardButton(text="🔍 Поиск", callback_data="quick:search"),
            ]
        ]
    )

    await message.answer(
        response,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )


def _extract_salary_short(text: str) -> str:
    """Короткое отображение зарплаты."""
    if not text:
        return ""

    # от X до Y
    match = re.search(r"от\s*(\d+)\s*\d*\s*(?:до\s*(\d+))?", text.lower())
    if match:
        low = match.group(1)
        high = match.group(2)
        if len(low) >= 4:
            low_k = int(low) // 1000
            if high and len(high) >= 4:
                high_k = int(high) // 1000
                return f"💰{low_k}-{high_k}к"
            return f"💰от {low_k}к"

    # Просто число с ₽/руб
    match = re.search(r"(\d{2,3})\s*(?:000|к|k)", text.lower())
    if match:
        return f"💰{match.group(1)}к"

    return ""


# ===== Быстрый поиск из кнопки =====


@router.callback_query(F.data == "quick:search", StateFilter("*"))
async def quick_search(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    from ..discovery.search import SearchState

    await callback.message.answer("🔍 Введите ключевое слово:", parse_mode="HTML")
    await state.set_state(SearchState.waiting_for_query)
