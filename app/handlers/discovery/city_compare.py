"""Фильтр по городу и сравнение вакансий."""

import re
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ...services.job_service import JobService
from ...database import async_session
from ...utils.categorizer import get_category_label

router = Router()

# Популярные города для быстрого фильтра
CITIES = {
    "moscow": {"label": "🏙 Москва", "patterns": ["москва", "moscow", "мск"]},
    "spb": {
        "label": "🌉 Санкт-Петербург",
        "patterns": ["петербург", "спб", "питер", "saint-petersburg"],
    },
    "remote": {
        "label": "🏠 Удалённо",
        "patterns": ["удалённ", "удаленн", "remote", "из дома"],
    },
    "novosibirsk": {"label": "🏔 Новосибирск", "patterns": ["новосибирск"]},
    "ekaterinburg": {"label": "🏭 Екатеринбург", "patterns": ["екатеринбург"]},
    "kazan": {"label": "🕌 Казань", "patterns": ["казань"]},
    "minsk": {"label": "🇧🇾 Минск", "patterns": ["минск"]},
    "almaty": {"label": "🇰🇿 Алматы", "patterns": ["алматы", "алма-ата"]},
}


@router.message(Command("city"))
async def cmd_city(message: types.Message):
    """Фильтр по городу."""
    buttons = []
    row = []
    for key, data in CITIES.items():
        row.append(
            InlineKeyboardButton(text=data["label"], callback_data=f"city:{key}")
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "🌍 <b>Фильтр по городу:</b>", parse_mode="HTML", reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("city:"))
async def callback_city(callback: types.CallbackQuery):
    city_key = callback.data.split(":")[1]
    city_data = CITIES.get(city_key)
    if not city_data:
        await callback.answer("Город не найден")
        return

    patterns = city_data["patterns"]
    label = city_data["label"]

    async with async_session() as session:
        job_service = JobService(session)
        all_jobs = await job_service.get_latest_jobs(limit=200)

    matching = []
    for job in all_jobs:
        text = f"{job.title} {job.description or ''}".lower()
        if any(p in text for p in patterns):
            matching.append(job)

    if not matching:
        await callback.message.edit_text(
            f"{label} — вакансий не найдено.\nПопробуйте другой город.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="city:back")]
                ]
            ),
        )
        await callback.answer()
        return

    response = f"{label}  •  <b>{len(matching)}</b> вакансий\n\n"
    for i, job in enumerate(matching[:10], 1):
        cat = get_category_label(job.category) if job.category else ""
        link = f"<a href='{job.link}'>→</a>" if job.link else ""
        response += f"<b>{i}.</b> {cat} {job.title[:60]}\n   {link}\n\n"

    if len(matching) > 10:
        response += f"... и ещё {len(matching) - 10}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Все города", callback_data="city:back")]
        ]
    )
    await callback.message.edit_text(
        response,
        parse_mode="HTML",
        disable_web_page_preview=True,
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "city:back")
async def city_back(callback: types.CallbackQuery):
    buttons = []
    row = []
    for key, data in CITIES.items():
        row.append(
            InlineKeyboardButton(text=data["label"], callback_data=f"city:{key}")
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "🌍 <b>Фильтр по городу:</b>", parse_mode="HTML", reply_markup=keyboard
    )
    await callback.answer()


# === Сравнение вакансий ===


@router.message(Command("compare"))
async def cmd_compare(message: types.Message):
    """Сравнение вакансий из избранного."""
    async with async_session() as session:
        job_service = JobService(session)
        favs = await job_service.get_favorites(message.from_user.id)

    if len(favs) < 2:
        await message.answer(
            "📊 Для сравнения нужно минимум 2 вакансии в ⭐ избранном."
        )
        return

    # Берём первые 5 для выбора
    buttons = []
    for job in favs[:5]:
        short = job.title[:35] + "…" if len(job.title) > 35 else job.title
        buttons.append(
            [InlineKeyboardButton(text=f"📋 {short}", callback_data=f"cmp1:{job.id}")]
        )

    buttons.append(
        [InlineKeyboardButton(text="◀️ В профиль", callback_data="profile:main")]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        "📊 <b>Сравнение вакансий</b>\n\nВыберите <b>первую</b> вакансию:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("cmp1:"))
async def callback_cmp1(callback: types.CallbackQuery):
    """Выбор первой вакансии для сравнения."""
    first_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        job_service = JobService(session)
        favs = await job_service.get_favorites(callback.from_user.id)

    buttons = []
    for job in favs[:5]:
        if job.id == first_id:
            continue
        short = job.title[:35] + "…" if len(job.title) > 35 else job.title
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"📋 {short}", callback_data=f"cmp2:{first_id}:{job.id}"
                )
            ]
        )

    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="compare:back_to_first")]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "📊 Выберите <b>вторую</b> вакансию:", parse_mode="HTML", reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "compare:back_to_first")
async def cb_compare_back(callback: types.CallbackQuery):
    await cmd_compare(callback.message)
    await callback.answer()


@router.callback_query(F.data.startswith("cmp2:"))
async def callback_cmp2(callback: types.CallbackQuery):
    """Результат сравнения."""
    parts = callback.data.split(":")
    id1, id2 = int(parts[1]), int(parts[2])

    async with async_session() as session:
        job_service = JobService(session)
        job1 = await job_service.get_job_by_id(id1)
        job2 = await job_service.get_job_by_id(id2)

    if not job1 or not job2:
        await callback.answer("Вакансия не найдена")
        return

    # Извлекаем зарплаты
    def _extract_salary(text):
        if not text:
            return "—"
        match = re.search(r"(\d[\d\s]*\d)\s*[-–]\s*(\d[\d\s]*\d)", text)
        if match:
            return f"{match.group(1).replace(' ', '')} – {match.group(2).replace(' ', '')}₽"
        match = re.search(r"от\s*(\d[\d\s]*\d)", text)
        if match:
            return f"от {match.group(1).replace(' ', '')}₽"
        return "—"

    cat1 = get_category_label(job1.category) if job1.category else "—"
    cat2 = get_category_label(job2.category) if job2.category else "—"
    src1 = job1.source or "—"
    src2 = job2.source or "—"
    sal1 = _extract_salary(f"{job1.title} {job1.description}")
    sal2 = _extract_salary(f"{job2.title} {job2.description}")
    time1 = job1.created_at.strftime("%d.%m") if job1.created_at else "—"
    time2 = job2.created_at.strftime("%d.%m") if job2.created_at else "—"

    response = (
        "📊 <b>Сравнение вакансий</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"  <b>A:</b> {job1.title[:50]}\n"
        f"  <b>B:</b> {job2.title[:50]}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📂 Категория\n   A: {cat1}\n   B: {cat2}\n\n"
        f"📍 Источник\n   A: {src1}\n   B: {src2}\n\n"
        f"💰 Зарплата\n   A: {sal1}\n   B: {sal2}\n\n"
        f"📅 Дата\n   A: {time1}\n   B: {time2}\n"
    )

    links = []
    if job1.link:
        links.append(InlineKeyboardButton(text="🔗 A", url=job1.link))
    if job2.link:
        links.append(InlineKeyboardButton(text="🔗 B", url=job2.link))

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            links if links else [],
            [
                InlineKeyboardButton(
                    text="◀️ Выбрать другие", callback_data="compare:back_to_first"
                )
            ],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="profile:main")],
        ]
    )

    await callback.message.edit_text(response, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()
