"""Аналитика рынка: топ навыков, зарплатная аналитика."""

import re
from collections import Counter
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from ...models.job import Job
from ...database import async_session
from ...utils.categorizer import get_category_label
from ...utils.resume_parser import SKILLS_DATABASE

router = Router()

TRACKED_SKILLS = list(SKILLS_DATABASE.keys())


# ===== /analytics — Единый хаб аналитики =====


@router.message(F.text == "📊 Аналитика")
@router.message(Command("analytics"))
async def cmd_analytics_hub(message: types.Message):
    """Главное меню аналитики."""
    text = (
        "📊 <b>Аналитика рынка IT</b>\n\n"
        "Выберите раздел для изучения статистики по вакансиям и рынку в целом:"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Зарплаты по рынкам", callback_data="analytics:salary"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏆 Топ-15 навыков", callback_data="analytics:skills_btn"
                ),
                InlineKeyboardButton(
                    text="📂 По категориям", callback_data="analytics:categories"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📈 По источникам", callback_data="analytics:sources"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📈 Комплексный Market Report",
                    callback_data="analytics:market_report",
                ),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data="hub:analytics"),
            ],
        ]
    )
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ===== /top_skills — Топ востребованных навыков =====


@router.message(Command("top_skills"))
@router.message(F.text == "🏆 Навыки")
async def cmd_top_skills(message: types.Message):
    """Анализ топ-15 навыков в вакансиях."""
    async with async_session() as session:
        result = await session.execute(select(Job.title, Job.description).limit(500))
        jobs = result.all()

    if not jobs:
        await message.answer("📭 Нет данных для анализа.")
        return

    skill_counter = Counter()
    for title, desc in jobs:
        text = f"{title} {desc or ''}".lower()
        for skill, patterns in SKILLS_DATABASE.items():
            for p in patterns:
                if p in text:
                    skill_counter[skill] += 1
                    break

    top = skill_counter.most_common(15)
    if not top:
        await message.answer("Навыков не найдено.")
        return

    max_count = top[0][1]
    text = "🏆 <b>Топ-15 навыков на рынке</b>\n\n"

    medals = ["🥇", "🥈", "🥉"]
    for i, (skill, count) in enumerate(top):
        medal = medals[i] if i < 3 else f"  {i + 1}."
        bar_len = int((count / max_count) * 12)
        bar = "▓" * bar_len + "░" * (12 - bar_len)
        pct = round(count / (len(jobs) or 1) * 100)
        text += f"{medal} <b>{skill}</b>\n"
        text += f"    <code>{bar}</code> {count} ({pct}%)\n\n"

    text += f"📊 Проанализировано: {len(jobs)} вакансий"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Зарплаты", callback_data="analytics:salary"
                ),
                InlineKeyboardButton(
                    text="📂 По категориям", callback_data="analytics:categories"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📈 По источникам", callback_data="analytics:sources"
                ),
                InlineKeyboardButton(
                    text="◀️ Назад в аналитику", callback_data="analytics:hub"
                ),
            ],
        ]
    )

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ===== Зарплатная аналитика =====


@router.message(Command("salary_analytics"))
@router.message(F.text == "💰 Зарплаты")
async def cmd_salary_analytics(message: types.Message):
    await _show_salary_analytics(message)


@router.callback_query(lambda c: c.data == "analytics:salary")
async def cb_salary_analytics(callback: types.CallbackQuery):
    await _show_salary_analytics(callback.message, edit=True)
    await callback.answer()


async def _show_salary_analytics(message, edit=False):
    """Средние зарплаты по категориям."""
    async with async_session() as session:
        result = await session.execute(
            select(Job.category, Job.description)
            .where(Job.description.isnot(None))
            .limit(500)
        )
        jobs = result.all()

    if not jobs:
        text = "📭 Нет данных."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    cat_salaries = {}
    for cat, desc in jobs:
        salary = _extract_salary_number(desc or "")
        if salary and cat:
            if cat not in cat_salaries:
                cat_salaries[cat] = []
            cat_salaries[cat].append(salary)

    if not cat_salaries:
        text = "💰 Зарплаты не указаны в текущих вакансиях."
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    text = "💰 <b>Зарплаты по категориям</b>\n\n"

    sorted_cats = sorted(
        cat_salaries.items(), key=lambda x: sum(x[1]) / (len(x[1]) or 1), reverse=True
    )

    for cat, salaries in sorted_cats[:10]:
        label = get_category_label(cat)
        avg = int(sum(salaries) / (len(salaries) or 1))
        min_s = min(salaries)
        max_s = max(salaries)
        count = len(salaries)

        avg_k = avg // 1000
        min_k = min_s // 1000
        max_k = max_s // 1000

        text += (
            f"{label}\n"
            f"  💰 <b>{avg_k}к</b> (от {min_k}к до {max_k}к) • {count} вакансий\n\n"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Навыки", callback_data="analytics:skills_btn"
                ),
                InlineKeyboardButton(
                    text="◀️ Назад в аналитику", callback_data="analytics:hub"
                ),
            ],
        ]
    )

    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(lambda c: c.data == "analytics:skills_btn")
async def cb_skills(callback: types.CallbackQuery):
    await cmd_top_skills(callback.message)
    await callback.answer()


# ===== Аналитика по источникам =====


@router.callback_query(lambda c: c.data == "analytics:sources")
async def cb_sources(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(Job.source, func.count(Job.id))
            .group_by(Job.source)
            .order_by(func.count(Job.id).desc())
        )
        sources = result.all()

        total = sum(cnt for _, cnt in sources)

    src_icons = {"hh.ru": "🏢", "habr.career": "💻", "kwork.ru": "🟠", "fl.ru": "🔵"}

    text = "📈 <b>Вакансии по источникам</b>\n\n"
    for source, count in sources:
        icon = src_icons.get(source, "📱")
        pct = round(count / (total or 1) * 100)
        bar_len = int(pct / 8)
        bar = "▓" * bar_len + "░" * (12 - bar_len)
        name = source if source in src_icons else f"@{source}"
        text += f"{icon} <b>{name}</b>\n"
        text += f"  <code>{bar}</code> {count} ({pct}%)\n\n"

    text += f"📦 Всего: <b>{total}</b>"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Навыки", callback_data="analytics:skills_btn"
                ),
                InlineKeyboardButton(
                    text="◀️ Назад в аналитику", callback_data="analytics:hub"
                ),
            ],
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== Аналитика по категориям =====


@router.callback_query(lambda c: c.data == "analytics:categories")
async def cb_categories(callback: types.CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(Job.category, func.count(Job.id))
            .group_by(Job.category)
            .order_by(func.count(Job.id).desc())
        )
        cats = result.all()

    total = sum(cnt for _, cnt in cats) or 1
    text = "📂 <b>Вакансии по категориям</b>\n\n"

    for cat, count in cats[:12]:
        label = get_category_label(cat)
        pct = round(count / total * 100)
        bar_len = int(pct / 8)
        bar = "▓" * bar_len + "░" * (12 - bar_len)
        text += f"{label}\n  <code>{bar}</code> {count} ({pct}%)\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Навыки", callback_data="analytics:skills_btn"
                ),
                InlineKeyboardButton(
                    text="◀️ Назад в аналитику", callback_data="analytics:hub"
                ),
            ],
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(lambda c: c.data == "analytics:market_report")
async def cb_market_report(callback: types.CallbackQuery):
    """Вызов market_report из хаба."""
    from ..discovery.market import cmd_market_report

    await cmd_market_report(callback.message)
    await callback.answer()


@router.callback_query(F.data == "analytics:hub")
async def cb_analytics_hub_back(callback: types.CallbackQuery):
    """Возврат в хаб аналитики."""
    await cmd_analytics_hub(callback.message)
    await callback.answer()


def _extract_salary_number(text: str) -> int:
    """Извлекает числовое значение зарплаты."""
    if not text:
        return 0

    patterns = [
        r"от\s*(\d[\d\s]*\d)\s*(?:₽|руб|rub)",
        r"до\s*(\d[\d\s]*\d)\s*(?:₽|руб|rub)",
        r"(\d{2,3})\s*(?:000|к|k)\s*(?:₽|руб|rub|р)?",
        r"(\d{5,6})\s*(?:₽|руб|rub|р)",
    ]
    for pat in patterns:
        match = re.search(pat, text.lower())
        if match:
            val = match.group(1).replace(" ", "")
            try:
                num = int(val)
                if num < 1000:
                    num *= 1000
                if 10000 <= num <= 1000000:
                    return num
            except ValueError:
                pass
    return 0
