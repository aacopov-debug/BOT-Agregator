from aiogram import Router, types, F
import html
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ...services.job_service import JobService
from ...services.channel_rating import get_channel_ratings, format_ratings
from ...services.digest import get_trends, format_trends
from ...database import async_session
from ...utils.categorizer import get_category_label, CATEGORY_RULES
from ...models.subscription import Subscription
from sqlalchemy import select

router = Router()

# === /search ===


class SearchState(StatesGroup):
    waiting_for_query = State()


class SalaryFilterState(StatesGroup):
    waiting_for_amount = State()


@router.message(Command("search"))
async def cmd_search(message: types.Message, state: FSMContext):
    from ...utils.keyboards import CANCEL_KEYBOARD

    await message.answer(
        "🔍 <b>Поиск вакансий</b>\n\n"
        "Введите запрос. Доступны операторы:\n"
        "• <code>python AND django</code>\n"
        "• <code>frontend OR react</code>\n"
        "• <code>devops NOT junior</code>\n"
        "• <code>python > 100000</code>\n\n"
        "Или просто слова:\n"
        "<code>python developer</code>",
        parse_mode="HTML",
        reply_markup=CANCEL_KEYBOARD,
    )
    await state.set_state(SearchState.waiting_for_query)


@router.message(SearchState.waiting_for_query)
async def process_search(
    message: types.Message, state: FSMContext, query_text: str = None
):
    # Если передан query_text (например, из голосового хендлера), используем его
    text = query_text or message.text

    if not text:
        return

    if text.startswith("/"):
        await state.clear()
        await message.answer("Поиск отменён.")
        return

    query = text.strip()
    async with async_session() as session:
        job_service = JobService(session)
        jobs = await job_service.search_jobs(query, limit=10)

    if not jobs:
        await message.answer(f"😔 По «{query}» ничего не найдено.")
        await state.clear()
        return

    response = f"🔍 <b>«{query}»</b>  •  {len(jobs)} результатов\n\n"
    for i, job in enumerate(jobs, 1):
        cat_label = get_category_label(job.category) if job.category else ""
        source = job.source or ""
        if source == "hh.ru":
            src = "🏢"
        elif source == "habr.career":
            src = "💻"
        else:
            src = "📱"
        safe_title = html.escape(job.title[:65])
        link = f"<a href='{job.link}'>→</a>" if job.link else ""
        response += (
            f"<b>{i}.</b> {cat_label} {safe_title}\n   {src} {source}  {link}\n\n"
        )

    # Сохраняем в историю
    from .market import save_search

    await save_search(message.from_user.id, query, len(jobs))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔔 Подписаться на этот поиск",
                    callback_data=f"sub:{query[:30]}",
                )
            ]
        ]
    )

    await message.answer(
        response,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )
    await state.clear()


@router.callback_query(F.data.startswith("sub:"))
async def cb_subscribe(callback: types.CallbackQuery):
    query = callback.data.split(":", 1)[1]

    async with async_session() as session:
        # Проверяем, есть ли уже
        existing = await session.execute(
            select(Subscription)
            .where(Subscription.user_telegram_id == callback.from_user.id)
            .where(Subscription.query == query)
        )
        if existing.scalar_one_or_none():
            await callback.answer(f"Вы уже подписаны на «{query}»!", show_alert=True)
            return

        # Считаем лимит (допустим 5)
        count = (
            (
                await session.execute(
                    select(Subscription).where(
                        Subscription.user_telegram_id == callback.from_user.id
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(count) >= 5:
            await callback.answer(
                "Максимум 5 активных подписок. Удалите старые в /subs.", show_alert=True
            )
            return

        sub = Subscription(user_telegram_id=callback.from_user.id, query=query)
        session.add(sub)
        await session.commit()

    await callback.answer(
        f"✅ Вы подписались на «{query}»! Теперь бот будет присылать уведомления.",
        show_alert=True,
    )


# === /subs ===


@router.message(Command("subs"))
async def cmd_subs(message: types.Message):
    async with async_session() as session:
        subs = (
            (
                await session.execute(
                    select(Subscription).where(
                        Subscription.user_telegram_id == message.from_user.id
                    )
                )
            )
            .scalars()
            .all()
        )

    if not subs:
        await message.answer(
            "🔔 <b>Умные подписки</b>\n\n"
            "У вас нет активных подписок на вакансии.\n"
            "Используйте /search, чтобы найти вакансии и подписаться на уведомления.",
            parse_mode="HTML",
        )
        return

    text = "🔔 <b>Ваши активные подписки:</b>\n\n"
    keyboard = []

    for i, sub in enumerate(subs, 1):
        text += f"{i}. <code>{sub.query}</code>\n"
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"❌ Удалить «{sub.query}»", callback_data=f"unsub:{sub.id}"
                )
            ]
        )

    markup = InlineKeyboardMarkup(
        inline_keyboard=keyboard
        + [
            [
                InlineKeyboardButton(
                    text="◀️ Назад в настройки", callback_data="menu:settings_btn"
                )
            ]
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.callback_query(F.data.startswith("unsub:"))
async def cb_unsubscribe(callback: types.CallbackQuery):
    await callback.answer()
    sub_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        # Проверим, принадлежит ли подписка юзеру
        sub = await session.get(Subscription, sub_id)
        if sub and sub.user_telegram_id == callback.from_user.id:
            await session.delete(sub)
            await session.commit()
            await callback.answer("Подписка удалена!")
            # Обновим список
            await cmd_subs(callback.message)
            await callback.message.delete()
        else:
            await callback.answer("Ошибка или подписка уже удалена.", show_alert=True)


# === /filter ===


@router.message(Command("filter"))
async def cmd_filter(message: types.Message):
    buttons = []
    row = []
    for key, data in CATEGORY_RULES.items():
        row.append(InlineKeyboardButton(text=data["label"], callback_data=f"cat:{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "📂 <b>Выберите категорию:</b>", parse_mode="HTML", reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("cat:"))
async def callback_category(callback: types.CallbackQuery):
    await callback.answer()
    category = callback.data.split(":")[1]
    label = get_category_label(category)

    async with async_session() as session:
        job_service = JobService(session)
        jobs = await job_service.get_jobs_by_category(category, limit=10)

    if not jobs:
        await callback.message.edit_text(f"😔 {label} — пока нет вакансий.")
        await callback.answer()
        return

    response = f"{label} <b>({len(jobs)}):</b>\n\n"
    for i, job in enumerate(jobs, 1):
        safe_title = html.escape(job.title[:65])
        link = f"<a href='{job.link}'>→</a>" if job.link else ""
        response += f"<b>{i}.</b> {safe_title}\n   {link}\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ К категориям", callback_data="cat:back_to_list"
                )
            ]
        ]
    )
    await callback.message.edit_text(
        response,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "cat:back_to_list", StateFilter("*"))
async def cb_cat_back(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    await cmd_filter(callback.message)


# === Salary Filter ===


@router.message(Command("salary_filter"))
async def cmd_salary_filter(message: types.Message, state: FSMContext):
    from ...utils.keyboards import CANCEL_KEYBOARD

    await message.answer(
        "💰 <b>Фильтр по зарплате</b>\n\n"
        "Введите минимальную зарплату (₽):\n"
        "<code>150000</code> или <code>200к</code>",
        parse_mode="HTML",
        reply_markup=CANCEL_KEYBOARD,
    )
    await state.set_state(SalaryFilterState.waiting_for_amount)


@router.message(SalaryFilterState.waiting_for_amount)
async def process_salary_filter(message: types.Message, state: FSMContext):
    import re

    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("Отменено.")
        return

    text = (
        message.text.strip()
        .lower()
        .replace("к", "000")
        .replace("k", "000")
        .replace(" ", "")
    )
    try:
        min_salary = int(text)
    except ValueError:
        await message.answer(
            "Введите число, например: <code>150000</code>", parse_mode="HTML"
        )
        return

    await state.clear()

    async with async_session() as session:
        job_service = JobService(session)
        all_jobs = await job_service.get_latest_jobs(limit=100)

    salary_pattern = re.compile(r"(\d[\d\s]*\d)")
    matching = []
    for job in all_jobs:
        desc = f"{job.title} {job.description or ''}"
        matches = salary_pattern.findall(desc)
        for m in matches:
            try:
                val = int(m.replace(" ", ""))
                if val >= min_salary and 10_000 <= val <= 1_000_000:
                    matching.append((val, job))
                    break
            except ValueError:
                pass

    matching.sort(key=lambda x: x[0], reverse=True)

    if not matching:
        await message.answer(f"😔 Вакансий с зарплатой от {min_salary:,}₽ не найдено.")
        return

    response = f"💰 <b>Вакансии от {min_salary:,}₽</b>  •  {len(matching)} шт.\n\n"
    for sal, job in matching[:10]:
        cat = get_category_label(job.category) if job.category else ""
        link = f"<a href='{job.link}'>→</a>" if job.link else ""
        response += f"<b>{sal:,}₽</b>  {job.title[:55]}\n   {cat}  {link}\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")]
        ]
    )

    await message.answer(
        response,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("similar:"), StateFilter("*"))
async def callback_similar(callback: types.CallbackQuery, state: FSMContext):
    """Показывает похожие вакансии."""
    await callback.answer()
    if state:
        await state.clear()
    job_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)
        if not job:
            await callback.answer("Не найдена")
            return

        # Ищем по той же категории
        similar = await job_service.get_jobs_by_category(
            job.category or "other", limit=6
        )
        # Исключаем текущую
        similar = [j for j in similar if j.id != job.id][:5]

    if not similar:
        await callback.answer("Похожих не найдено")
        return

    response = f"🔄 <b>Похожие на:</b> <i>{job.title[:50]}</i>\n\n"
    for i, j in enumerate(similar, 1):
        cat = get_category_label(j.category) if j.category else ""
        link = f"<a href='{j.link}'>→</a>" if j.link else ""
        response += f"<b>{i}.</b> {cat} {j.title[:60]}\n   {link}\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data=f"detail:{job_id}")]
        ]
    )

    await callback.message.edit_text(
        response,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )
    await callback.answer()


# === /stats ===


@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    async with async_session() as session:
        job_service = JobService(session)
        total = await job_service.count_jobs()
        by_category = await job_service.count_by_category()

    response = f"📊 <b>Статистика</b>\n\nВсего вакансий: <b>{total}</b>\n\n"

    if by_category:
        response += "<b>По категориям:</b>\n"
        for cat, count in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
            label = get_category_label(cat)
            response += f"  {label}: {count}\n"
        response += "\n"

    ratings = await get_channel_ratings()
    response += format_ratings(ratings)

    await message.answer(response, parse_mode="HTML")


# === /rating ===


@router.message(Command("rating"))
async def cmd_rating(message: types.Message):
    ratings = await get_channel_ratings()
    text = format_ratings(ratings)
    if not ratings:
        text = "📊 Нет данных. Подождите, пока бот соберёт вакансии."
    await message.answer(text, parse_mode="HTML")


# === /trends ===


@router.message(Command("trends"))
async def cmd_trends(message: types.Message):
    """Тренды вакансий за неделю."""
    trends = await get_trends()
    text = format_trends(trends)
    await message.answer(text, parse_mode="HTML")
