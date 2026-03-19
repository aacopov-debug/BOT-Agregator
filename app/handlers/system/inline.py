"""Inline-режим: поиск вакансий из любого чата через @botname запрос."""

from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
from ...services.job_service import JobService
from ...database import async_session
from ...utils.categorizer import get_category_label
import hashlib

router = Router()


@router.inline_query()
async def inline_search(query: InlineQuery):
    """Обработка inline-запросов: @botname python"""
    text = query.query.strip()
    if len(text) < 2:
        return

    async with async_session() as session:
        job_service = JobService(session)
        jobs = await job_service.search_jobs(text, limit=10)

    results = []
    for job in jobs:
        cat_label = get_category_label(job.category) if job.category else ""
        source = (
            f"@{job.source}"
            if job.source and job.source != "hh.ru"
            else (job.source or "")
        )
        desc = job.description[:200] if job.description else "Нет описания"
        link_text = f"\n🔗 {job.link}" if job.link else ""

        content = InputTextMessageContent(
            message_text=(
                f"📋 <b>{job.title}</b>\n"
                f"{cat_label}  {source}\n\n"
                f"{desc}...\n"
                f"{link_text}"
            ),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

        uid = hashlib.md5(f"{job.id}".encode()).hexdigest()
        results.append(
            InlineQueryResultArticle(
                id=uid,
                title=job.title[:60],
                description=f"{cat_label} {source} — {desc[:80]}",
                input_message_content=content,
            )
        )

    await query.answer(results, cache_time=60, is_personal=True)
