"""История поиска и рыночный отчёт."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, select, func
from sqlalchemy.sql import func as sqf
from ...database import Base, async_session
from ...models.job import Job
from ...utils.categorizer import get_category_label
from ...utils.resume_parser import SKILLS_DATABASE

router = Router()


class SearchHistory(Base):
    __tablename__ = "search_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(BigInteger, nullable=False, index=True)
    query = Column(String(255), nullable=False)
    results_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=sqf.now())


async def save_search(user_id: int, query: str, count: int):
    """Сохраняет поисковый запрос в историю."""
    async with async_session() as session:
        entry = SearchHistory(
            user_telegram_id=user_id,
            query=query[:255],
            results_count=count,
        )
        session.add(entry)
        await session.commit()


# ===== /history — история поиска =====


@router.message(Command("history"))
async def cmd_history(message: types.Message):
    """Показать историю поиска."""
    async with async_session() as session:
        entries = (
            (
                await session.execute(
                    select(SearchHistory)
                    .where(SearchHistory.user_telegram_id == message.from_user.id)
                    .order_by(SearchHistory.created_at.desc())
                    .limit(15)
                )
            )
            .scalars()
            .all()
        )

    if not entries:
        await message.answer(
            "🔍 <b>История поиска пуста</b>\n\n"
            "Используйте /search для поиска вакансий.",
            parse_mode="HTML",
        )
        return

    text = f"🔍 <b>История поиска</b> ({len(entries)})\n\n"
    buttons = []
    for e in entries:
        time_str = e.created_at.strftime("%d.%m %H:%M") if e.created_at else ""
        text += f"  🔹 <code>{e.query}</code> → {e.results_count} рез. ({time_str})\n"
        buttons.append(
            InlineKeyboardButton(
                text=f"🔄 {e.query[:20]}", callback_data=f"hsearch:{e.query[:30]}"
            )
        )

    # Кнопки по 2 в ряд
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append(
        [InlineKeyboardButton(text="🗑 Очистить", callback_data="history:clear")]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("hsearch:"))
async def cb_history_search(callback: types.CallbackQuery):
    """Повторный поиск из истории."""
    query = callback.data[8:]  # после "hsearch:"
    from ...services.job_service import JobService

    async with async_session() as session:
        js = JobService(session)
        jobs = await js.search_jobs(query, limit=10)

    if not jobs:
        await callback.answer(f"Ничего не найдено: {query}")
        return

    text = f"🔍 <b>Повторный поиск:</b> <code>{query}</code>\n\n"
    for i, job in enumerate(jobs[:10], 1):
        cat = get_category_label(job.category) if job.category else ""
        link = f"<a href='{job.link}'>→</a>" if job.link else ""
        text += f"<b>{i}.</b> {cat} {job.title[:60]} {link}\n"

    text += f"\n📊 Найдено: {len(jobs)}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ К истории", callback_data="history:back_to_list"
                )
            ]
        ]
    )
    await callback.message.edit_text(
        text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "history:back_to_list")
async def cb_history_back(callback: types.CallbackQuery):
    await cmd_history(callback.message)
    await callback.answer()


@router.callback_query(F.data == "history:clear")
async def cb_history_clear(callback: types.CallbackQuery):
    """Очистить историю."""
    from sqlalchemy import delete

    async with async_session() as session:
        await session.execute(
            delete(SearchHistory).where(
                SearchHistory.user_telegram_id == callback.from_user.id
            )
        )
        await session.commit()
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Найти вакансии", callback_data="menu:search_btn"
                )
            ]
        ]
    )
    await callback.message.edit_text("🗑 История поиска очищена.", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "menu:search_btn")
async def cb_menu_search(callback: types.CallbackQuery, state: FSMContext):
    from ..system.start import btn_search  # UPDATED RELATIVE PATH

    await btn_search(callback.message, state)
    await callback.answer()


# ===== /market_report — рыночный отчёт =====


@router.message(Command("market_report"))
async def cmd_market_report(message: types.Message):
    """Комплексный отчёт о рынке вакансий."""
    async with async_session() as session:
        # Общая статистика
        total = (await session.execute(select(func.count(Job.id)))).scalar_one()

        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)
        cutoff_7d = now - timedelta(days=7)

        new_24h = (
            await session.execute(
                select(func.count(Job.id)).where(Job.created_at >= cutoff_24h)
            )
        ).scalar_one()

        new_7d = (
            await session.execute(
                select(func.count(Job.id)).where(Job.created_at >= cutoff_7d)
            )
        ).scalar_one()

        # Топ категории
        cats = (
            await session.execute(
                select(Job.category, func.count(Job.id))
                .group_by(Job.category)
                .order_by(func.count(Job.id).desc())
                .limit(5)
            )
        ).all()

        # Топ источники
        sources = (
            await session.execute(
                select(Job.source, func.count(Job.id))
                .group_by(Job.source)
                .order_by(func.count(Job.id).desc())
            )
        ).all()

        # Последние вакансии для анализа навыков
        recent = (
            await session.execute(
                select(Job.title, Job.description)
                .where(Job.created_at >= cutoff_7d)
                .limit(300)
            )
        ).all()

    # Анализ навыков
    skill_counter = Counter()
    for title, desc in recent:
        text = f"{title} {desc or ''}".lower()
        for skill, patterns in SKILLS_DATABASE.items():
            for p in patterns:
                if p in text:
                    skill_counter[skill] += 1
                    break

    top_skills = skill_counter.most_common(8)

    # Формируем отчёт
    src_icons = {
        "hh.ru": "🏢",
        "habr.career": "💻",
        "kwork.ru": "🟠",
        "fl.ru": "🔵",
        "superjob.ru": "🟣",
    }

    report = (
        "📊 <b>Рыночный отчёт</b>\n"
        f"📅 {datetime.now().strftime('%d.%m.%Y')}\n\n"
        "━━━ <b>Общая картина</b> ━━━\n"
        f"📦 Всего вакансий: <b>{total}</b>\n"
        f"🆕 За 24 часа: <b>{new_24h}</b>\n"
        f"📅 За неделю: <b>{new_7d}</b>\n"
        f"📈 В день: ~<b>{new_7d // 7 if new_7d > 0 else 0}</b>\n\n"
    )

    report += "━━━ <b>🏢 Источники</b> ━━━\n"
    for src, cnt in sources:
        icon = src_icons.get(src, "📱")
        pct = round(cnt / total * 100) if total else 0
        report += f"  {icon} {src}: <b>{cnt}</b> ({pct}%)\n"

    report += "\n━━━ <b>📂 Топ категорий</b> ━━━\n"
    for cat, cnt in cats:
        label = get_category_label(cat)
        report += f"  {label}: <b>{cnt}</b>\n"

    if top_skills:
        report += "\n━━━ <b>🏆 Топ навыков (7д)</b> ━━━\n"
        medals = ["🥇", "🥈", "🥉"]
        for i, (skill, cnt) in enumerate(top_skills):
            medal = medals[i] if i < 3 else f"  {i + 1}."
            report += f"  {medal} {skill}: <b>{cnt}</b>\n"

    # Рекомендации
    if top_skills:
        top_skill = top_skills[0][0]
        report += (
            f"\n━━━ <b>💡 Рекомендация</b> ━━━\n"
            f"Самый востребованный навык — <b>{top_skill}</b>.\n"
            f"Прокачайте его для максимальной конкурентоспособности!"
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏆 Навыки", callback_data="analytics:skills_btn"
                ),
                InlineKeyboardButton(
                    text="💰 Зарплаты", callback_data="analytics:salary"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔊 Озвучить отчет", callback_data="tts:market:0"
                ),
            ],
            [
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile:main"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="menu:start"),
            ],
        ]
    )

    await message.answer(report, parse_mode="HTML", reply_markup=keyboard)
