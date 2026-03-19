"""Утилиты: /share, /random, дедупликация."""

import random as rnd
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func
from ...services.job_service import JobService
from ...models.job import Job
from ...database import async_session
from ...utils.categorizer import get_category_label

router = Router()


# ===== /random — Случайная вакансия =====


@router.message(Command("random"))
@router.message(F.text == "🎲 Случайная")
async def cmd_random(message: types.Message):
    """Случайная вакансия — для вдохновения."""
    async with async_session() as session:
        total = (await session.execute(select(func.count(Job.id)))).scalar_one()
        if total == 0:
            await message.answer("📭 БД пуста. Подождите скрапинга.")
            return

        offset = rnd.randint(0, max(0, total - 1))
        stmt = select(Job).offset(offset).limit(1)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

    if not job:
        await message.answer("Не удалось найти вакансию.")
        return

    cat = get_category_label(job.category) if job.category else ""
    src_icons = {"hh.ru": "🏢", "habr.career": "💻", "kwork.ru": "🟠"}
    src = src_icons.get(job.source, "📱")
    desc = (job.description or "")[:400]

    text = (
        f"🎲 <b>Случайная вакансия</b>\n\n"
        f"<b>{job.title}</b>\n"
        f"{src} {job.source} • {cat}\n\n"
        f"{desc}\n"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Избранное", callback_data=f"fav:{job.id}"
                ),
                InlineKeyboardButton(
                    text="📩 Откликнуться", callback_data=f"apply:{job.id}"
                ),
            ],
            [
                InlineKeyboardButton(text="🔗 Открыть", url=job.link)
                if job.link
                else InlineKeyboardButton(text="—", callback_data="noop"),
                InlineKeyboardButton(text="🎲 Ещё", callback_data="random:next"),
            ],
        ]
    )

    await message.answer(
        text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )


@router.callback_query(F.data == "random:next")
async def random_next(callback: types.CallbackQuery):
    """Ещё одна случайная вакансия."""
    async with async_session() as session:
        total = (await session.execute(select(func.count(Job.id)))).scalar_one()
        if total == 0:
            await callback.answer("БД пуста")
            return

        offset = rnd.randint(0, max(0, total - 1))
        stmt = select(Job).offset(offset).limit(1)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()

    if not job:
        await callback.answer("Ошибка")
        return

    cat = get_category_label(job.category) if job.category else ""
    src_icons = {"hh.ru": "🏢", "habr.career": "💻", "kwork.ru": "🟠"}
    src = src_icons.get(job.source, "📱")
    desc = (job.description or "")[:400]

    text = (
        f"🎲 <b>Случайная вакансия</b>\n\n"
        f"<b>{job.title}</b>\n"
        f"{src} {job.source} • {cat}\n\n"
        f"{desc}\n"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⭐ Избранное", callback_data=f"fav:{job.id}"
                ),
                InlineKeyboardButton(
                    text="📩 Откликнуться", callback_data=f"apply:{job.id}"
                ),
            ],
            [
                InlineKeyboardButton(text="🔗 Открыть", url=job.link)
                if job.link
                else InlineKeyboardButton(text="—", callback_data="noop"),
                InlineKeyboardButton(text="🎲 Ещё", callback_data="random:next"),
            ],
        ]
    )

    await callback.message.edit_text(
        text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "noop")
async def noop(callback: types.CallbackQuery):
    await callback.answer()


# ===== Поделиться вакансией =====


@router.callback_query(F.data.startswith("share:"))
async def share_job(callback: types.CallbackQuery):
    """Генерирует ссылку для пересылки вакансии."""
    job_id = int(callback.data.split(":")[1])

    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)

    if not job:
        await callback.answer("Вакансия не найдена")
        return

    cat = get_category_label(job.category) if job.category else ""
    src_icons = {"hh.ru": "🏢", "habr.career": "💻", "kwork.ru": "🟠"}
    src = src_icons.get(job.source, "📱")

    share_text = (
        f"💼 {job.title}\n"
        f"{src} {job.source} • {cat}\n\n"
        f"{(job.description or '')[:200]}\n\n"
        f"🔗 {job.link or 'Ссылка недоступна'}\n\n"
        f"📱 Найдено через @job_aggregator_bot"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Переслать другу", switch_inline_query=job.title[:50]
                )
            ],
        ]
    )

    await callback.message.answer(share_text, reply_markup=keyboard)
    await callback.answer("📤 Скопируйте или перешлите!")


# ===== Дедупликация =====


async def deduplicate_jobs():
    """Удаляет дубликаты вакансий (совпадающие title+source)."""
    from sqlalchemy import delete as sql_delete

    async with async_session() as session:
        subq = (
            select(func.min(Job.id).label("keep_id"), Job.title, Job.source)
            .group_by(Job.title, Job.source)
            .having(func.count(Job.id) > 1)
        ).subquery()

        dupes_stmt = (
            select(Job.id)
            .join(subq, (Job.title == subq.c.title) & (Job.source == subq.c.source))
            .where(Job.id != subq.c.keep_id)
        )
        dupe_result = await session.execute(dupes_stmt)
        dupe_ids = [row[0] for row in dupe_result.all()]

        if dupe_ids:
            stmt = sql_delete(Job).where(Job.id.in_(dupe_ids))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    return 0
