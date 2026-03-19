"""Просмотр вакансий с улучшенными карточками."""

from aiogram import Router, types, F
import html
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ...services.job_service import JobService
from ...database import async_session
from ...utils.categorizer import get_category_label
from ...services.user_service import UserService
from ...services.ai_cover_letter import generate_cover_letter
from ...utils.resume_parser import parse_resume, match_score
from ...models.application import Application
from ...services.ai_matcher import AIMatcherService

router = Router()
JOBS_PER_PAGE = 5


def _format_job_card(job, index, compact=False):
    """Форматирует одну вакансию для вывода."""
    cat_label = f"[{get_category_label(job.category)}]" if job.category else ""
    source_label = f"🏷 {job.source}" if job.source else "📱 Источник"

    # Добавляем скор совпадения, если переданы ключевые слова пользователя
    score_text = ""
    user_keywords = getattr(job, "_user_keywords", None)
    if compact and user_keywords:
        try:
            profile = parse_resume(user_keywords)
            score = match_score(profile, job.title, job.description or "")
            if score > 15:
                bar = "🟢" if score >= 70 else ("🟡" if score >= 40 else "🔴")
                score_text = f" | {bar} <b>{score:.0f}%</b>"
        except Exception:
            pass

    if compact:
        # Короткая карточка для списка
        title = html.escape(job.title[:70])
        link_text = f"<a href='{job.link}'>→</a>" if job.link else ""
        # Бейдж свежести
        fresh = ""
        if job.created_at:
            from datetime import datetime, timedelta, timezone

            age = datetime.now(timezone.utc) - job.created_at
            if age < timedelta(hours=6):
                fresh = "🆕 "
            elif age < timedelta(hours=24):
                fresh = "🔥 "
        return (
            f"<b>{index}.</b> {fresh}{cat_label} <b>{title}</b>\n"
            f"    {source_label}{score_text} {link_text}\n"
        )
    else:
        # Полная карточка
        safe_title = html.escape(job.title)
        safe_desc = (
            html.escape(job.description[:1200]) if job.description else "Нет описания"
        )
        link_text = (
            f"\n🔗 <a href='{job.link}'>Перейти к вакансии</a>" if job.link else ""
        )
        time_str = job.created_at.strftime("%d.%m %H:%M") if job.created_at else ""
        return (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{cat_label} <b>{safe_title}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📍 Источник: {source_label}\n"
            f"🕐 {time_str}\n\n"
            f"{safe_desc}\n"
            f"{link_text}"
        )


def _build_job_page(
    jobs: list, page: int, total: int
) -> tuple[str, InlineKeyboardMarkup]:
    """Формирует страницу вакансий."""
    total_pages = max(1, (total + JOBS_PER_PAGE - 1) // JOBS_PER_PAGE)

    if not jobs:
        return "😔 Пока вакансий нет. Бот собирает данные — попробуйте позже!", None

    response = (
        f"📋 <b>Вакансии</b>\n"
        f"📄 Стр. {page + 1} из {total_pages}  •  Всего: {total}\n\n"
    )
    for i, job in enumerate(jobs, start=page * JOBS_PER_PAGE + 1):
        response += _format_job_card(job, i, compact=True) + "\n"

    rows = []
    # Кнопки ⭐ и 📄 для каждой вакансии
    for job in jobs:
        short_title = job.title[:20] + "…" if len(job.title) > 20 else job.title
        rows.append(
            [
                InlineKeyboardButton(text="⭐", callback_data=f"fav:add:{job.id}"),
                InlineKeyboardButton(
                    text=f"📄 {short_title}", callback_data=f"detail:{job.id}"
                ),
            ]
        )

    # Навигация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"jobs_page:{page - 1}")
        )
    nav_buttons.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"jobs_page:{page + 1}")
        )
    rows.append(nav_buttons)

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    return response, keyboard


@router.message(Command("jobs"))
async def cmd_jobs(message: types.Message):
    async with async_session() as session:
        job_service = JobService(session)
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            message.from_user.id, message.from_user.username
        )

        total = await job_service.count_jobs()
        jobs = await job_service.get_jobs_page(page=0, per_page=JOBS_PER_PAGE)

        if user and user.keywords:
            for job in jobs:
                job._user_keywords = user.keywords

    text, keyboard = _build_job_page(jobs, page=0, total=total)
    await message.answer(
        text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("jobs_page:"), StateFilter("*"))
async def callback_jobs_page(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    page = int(callback.data.split(":")[1])
    async with async_session() as session:
        job_service = JobService(session)
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            callback.from_user.id, callback.from_user.username
        )

        total = await job_service.count_jobs()
        jobs = await job_service.get_jobs_page(page=page, per_page=JOBS_PER_PAGE)

        if user and user.keywords:
            for job in jobs:
                job._user_keywords = user.keywords

    text, keyboard = _build_job_page(jobs, page=page, total=total)
    await callback.message.edit_text(
        text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def callback_noop(callback: types.CallbackQuery):
    await callback.answer()


@router.callback_query(F.data.startswith("detail:"), StateFilter("*"))
async def callback_detail(callback: types.CallbackQuery, state: FSMContext):
    """Полная карточка вакансии."""
    await callback.answer()
    if state:
        await state.clear()
    job_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)

        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            callback.from_user.id, callback.from_user.username
        )

        # --- ПРОВЕРКА ЛИМИТОВ (МОНЕТИЗАЦИЯ) ---
        from datetime import date, datetime, timezone

        today = date.today()
        is_prem = (user.role == "admin") or (
            user.is_premium
            and user.premium_until
            and user.premium_until > datetime.now(timezone.utc)
        )

        if not is_prem:
            # Сброс счетчика, если новый день
            if user.last_view_date != today:
                user.daily_views = 0
                user.last_view_date = today

            # Проверка лимита (2 вакансии в день для бесплатных)
            LIMIT = 2
            if user.daily_views >= LIMIT:
                await callback.answer(
                    f"⚠️ Бесплатный лимит исчерпан ({LIMIT}/{LIMIT}).\n\n"
                    "💎 Ты упускаешь лучшие вакансии! Подключи Premium, чтобы просматривать всё без ограничений и получать AI-анализ.",
                    show_alert=True,
                )
                return

            # Учитываем просмотр
            user.daily_views += 1
            await session.commit()
        # --------------------------------------

    if not job:
        await callback.answer("Вакансия не найдена")
        return

    text = _format_job_card(job, index=0, compact=False)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ В избранное", callback_data=f"fav:add:{job.id}"
                ),
                InlineKeyboardButton(
                    text="📤 Быстрый отклик", callback_data=f"quickapply:{job.id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Похожие", callback_data=f"similar:{job.id}"
                ),
                InlineKeyboardButton(
                    text="📤 Поделиться", callback_data=f"share:{job.id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💬 Спросить AI", callback_data=f"ask_ai:{job.id}"
                ),
                InlineKeyboardButton(
                    text="🎤 Интервью", callback_data=f"interview:{job.id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📝 AI Письмо", callback_data=f"cover:{job.id}"
                ),
                InlineKeyboardButton(
                    text="🔊 Озвучить", callback_data=f"tts:job:{job.id}"
                ),
                InlineKeyboardButton(text="⏰", callback_data=f"remind:{job.id}"),
            ],
            [
                InlineKeyboardButton(
                    text="🎯 AI Анализ совпадения", callback_data=f"aimatch:{job.id}"
                ),
            ],
            [
                InlineKeyboardButton(text="◀️ К списку", callback_data="jobs_page:0"),
            ],
        ]
    )

    await callback.message.edit_text(
        text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("cover:"))
async def cb_generate_cover(callback: types.CallbackQuery):
    await callback.answer("⏳ Нейросеть пишет письмо...", show_alert=False)
    job_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)

        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            callback.from_user.id, callback.from_user.username
        )

    if not job:
        await callback.message.edit_text("Вакансия больше недоступна.")
        return

    text = await generate_cover_letter(user, job)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Назад к вакансии", callback_data=f"detail:{job.id}"
                )
            ]
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("quickapply:"))
async def cb_quick_apply(callback: types.CallbackQuery):
    """Быстрый Отклик: AI-письмо + ссылка + авто-трекинг."""
    await callback.answer("⏳ AI готовит отклик...", show_alert=False)
    job_id = int(callback.data.split(":")[1])

    user_id = callback.from_user.id
    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            user_id, callback.from_user.username
        )

    if not job:
        await callback.message.edit_text("❌ Вакансия больше недоступна.")
        return

    # 1) Генерируем AI-письмо
    letter = await generate_cover_letter(user, job)

    # 2) Авто-трекинг (добавляем в трекер, если ещё нет)
    async with async_session() as session:
        from sqlalchemy import select as sa_select

        existing = (
            await session.execute(
                sa_select(Application).where(
                    Application.user_telegram_id == user_id,
                    Application.job_id == job_id,
                )
            )
        ).scalar_one_or_none()
        if not existing:
            app = Application(user_telegram_id=user_id, job_id=job_id, status="applied")
            session.add(app)
            await session.commit()
            track_msg = "✅ Отклик автоматически сохранён в трекере!"
        else:
            track_msg = "📌 Уже есть в трекере"

    # 3) Формируем сообщение
    text = (
        f"📤 <b>Быстрый отклик</b> — <b>{job.title[:60]}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{letter}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"{track_msg}\n\n"
        f"💡 <i>Длительно нажмите на текст письма → Скопировать, затем </i>\n"
        f"💡 <i>нажмите кнопку ниже и вставьте письмо на сайте.</i>"
    )

    # 4) Кнопки: ссылка на вакансию + назад
    buttons = []
    if job.link:
        buttons.append(
            [
                InlineKeyboardButton(
                    text="🔗 Открыть вакансию и откликнуться", url=job.link
                )
            ]
        )
    buttons.append(
        [
            InlineKeyboardButton(text="📋 Мои отклики", callback_data="tracker:list"),
            InlineKeyboardButton(text="◀️ Назад", callback_data=f"detail:{job.id}"),
        ]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("aimatch:"))
async def cb_aimatch(callback: types.CallbackQuery):
    """Глубокий AI анализ соответствия резюме вакансии."""
    job_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    await callback.answer(
        "⏳ AI анализирует ваше резюме и требования вакансии...", show_alert=True
    )

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)

        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            user_id, callback.from_user.username
        )

    if not job:
        await callback.message.edit_text("❌ Вакансия больше недоступна.")
        return

    if not user.keywords:
        await callback.message.answer(
            "❌ Сначала загрузите резюме или укажите навыки через /resume"
        )
        return

    # Проверка баланса (как в сопроводительных письмах)
    async with async_session() as session:
        from ...models.user import User
        from sqlalchemy import select

        db_user = (
            await session.execute(select(User).where(User.telegram_id == user_id))
        ).scalar_one_or_none()

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        is_prem = (db_user.role == "admin") or (
            db_user.is_premium and db_user.premium_until and db_user.premium_until > now
        )

        if db_user.ai_credits < 1 and not is_prem:
            await callback.answer(
                "❌ У вас закончились AI-кредиты.\nПополните баланс командой /balance",
                show_alert=True,
            )
            return

        # Списываем кредит
        if not is_prem:
            db_user.ai_credits -= 1
            await session.commit()

    matcher = AIMatcherService()
    analysis = await matcher.analyze_match(user.keywords, job)

    if not analysis:
        # Возвращаем кредит при ошибке
        async with async_session() as session:
            db_user = (
                await session.execute(select(User).where(User.telegram_id == user_id))
            ).scalar_one_or_none()
            if db_user:
                db_user.ai_credits += 1
                await session.commit()
        await callback.message.answer("❌ AI временно недоступен. Кредит возвращен.")
        return

    # Формируем красивый вывод
    score = analysis.get("score", 0)
    bar = "🟢" if score >= 70 else ("🟡" if score >= 40 else "🔴")

    pros = "\n".join([f"✅ {p}" for p in analysis.get("pros", [])])
    cons = "\n".join([f"⚠️ {c}" for c in analysis.get("cons", [])])

    text = (
        f"🎯 <b>AI Анализ соответствия: {score}%</b> {bar}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💪 <b>Сильные стороны:</b>\n{pros}\n\n"
        f"🧐 <b>Чего не хватает:</b>\n{cons}\n\n"
        f"📝 <b>Резюме:</b>\n{analysis.get('summary', '')}\n\n"
        f"💡 <b>Совет:</b>\n{analysis.get('advice', '')}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<i>Иерархия: {bar} {score}% соответствия</i>"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 AI Письмо", callback_data=f"cover:{job.id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="◀️ Назад к вакансии", callback_data=f"detail:{job.id}"
                )
            ],
        ]
    )

    await callback.message.answer(text, parse_mode="HTML", reply_markup=keyboard)
