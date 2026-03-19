"""Экспорт избранного, подписка на категории, аналитика зарплат."""

import re
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from ...services.job_service import JobService
from ...services.user_service import UserService
from ...database import async_session
from ...utils.categorizer import get_category_label, CATEGORY_RULES

router = Router()


# === /export — экспорт избранного в файл ===


@router.message(Command("export"))
async def cmd_export(message: types.Message, user_id: int = None):
    """Экспортирует избранные вакансии в TXT и HTML."""
    uid = user_id or message.from_user.id
    async with async_session() as session:
        job_service = JobService(session)
        jobs = await job_service.get_favorites(uid)

    if not jobs:
        await message.answer(
            "⭐ Избранное пусто. Добавьте вакансии кнопкой ⭐ в /jobs."
        )
        return

    # TXT-файл
    lines = [f"⭐ Избранные вакансии ({len(jobs)})\n", "=" * 50 + "\n\n"]
    for i, job in enumerate(jobs, 1):
        cat = get_category_label(job.category) if job.category else ""
        source = job.source or ""
        lines.append(f"{i}. {job.title}\n")
        lines.append(f"   Категория: {cat}\n")
        lines.append(f"   Источник: {source}\n")
        if job.link:
            lines.append(f"   Ссылка: {job.link}\n")
        if job.description:
            lines.append(f"   {job.description[:300]}...\n")
        lines.append("\n" + "-" * 40 + "\n\n")

    txt_content = "".join(lines).encode("utf-8")
    txt_doc = BufferedInputFile(txt_content, filename="favorites.txt")

    # HTML файл
    html_rows = ""
    for i, job in enumerate(jobs, 1):
        cat = get_category_label(job.category) if job.category else "—"
        link = f'<a href="{job.link}">Открыть →</a>' if job.link else "—"
        desc = (job.description or "")[:200]
        html_rows += f"""
        <tr>
            <td>{i}</td>
            <td><strong>{job.title}</strong><br><small>{desc}...</small></td>
            <td>{cat}</td>
            <td>{job.source or "—"}</td>
            <td>{link}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<title>Избранные вакансии</title>
<style>
body {{ font-family: 'Segoe UI', sans-serif; margin: 30px; color: #333; }}
h1 {{ color: #667eea; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
th {{ background: #667eea; color: #fff; padding: 10px; text-align: left; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #eee; vertical-align: top; }}
tr:hover {{ background: #f5f5ff; }}
a {{ color: #667eea; }}
small {{ color: #888; }}
.footer {{ margin-top: 30px; color: #999; font-size: 0.85em; }}
@media print {{ body {{ margin: 10mm; }} }}
</style></head><body>
<h1>⭐ Избранные вакансии ({len(jobs)})</h1>
<table><thead><tr>
<th>#</th><th>Вакансия</th><th>Категория</th><th>Источник</th><th>Ссылка</th>
</tr></thead><tbody>{html_rows}</tbody></table>
<p class="footer">Job Aggregator Bot • Экспорт избранного</p>
</body></html>"""

    html_doc = BufferedInputFile(html.encode("utf-8"), filename="favorites.html")

    await message.answer_document(txt_doc, caption=f"📄 TXT: {len(jobs)} вакансий")
    await message.answer_document(
        html_doc, caption="🌐 HTML: откройте в браузере → Ctrl+P → PDF"
    )


# === /subscribe — подписка на категории ===


@router.message(Command("subscribe"))
async def cmd_subscribe(
    message: types.Message, user_id: int = None, username: str = None
):
    """Выбор категорий для автоматических уведомлений."""
    uid = user_id or message.from_user.id
    uname = username or message.from_user.username
    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(telegram_id=uid, username=uname)

    current = user.keywords or ""

    buttons = []
    row = []
    for key, data in CATEGORY_RULES.items():
        is_sub = key in current.lower()
        prefix = "✅ " if is_sub else ""
        row.append(
            InlineKeyboardButton(
                text=f"{prefix}{data['label']}", callback_data=f"sub:{key}"
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="✔️ Готово", callback_data="sub:done")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"📬 <b>Подписка на категории</b>\n\n"
        f"Нажимайте на категории, чтобы включить/выключить уведомления.\n"
        f"Текущие: <code>{current if current else 'не настроены'}</code>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("sub:"))
async def callback_subscribe(callback: types.CallbackQuery):
    action = callback.data.split(":")[1]

    if action == "done":
        await callback.message.edit_text("✅ Подписка сохранена!")
        await callback.answer()
        return

    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            telegram_id=callback.from_user.id, username=callback.from_user.username
        )

        current = user.keywords or ""
        categories = [c.strip() for c in current.split(",") if c.strip()]

        if action in categories:
            categories.remove(action)
        else:
            categories.append(action)

        new_keywords = ", ".join(categories)
        await user_service.update_keywords(callback.from_user.id, new_keywords)

    await callback.answer(
        f"{'➕ Добавлено' if action in categories else '➖ Убрано'}: {get_category_label(action)}"
    )

    buttons = []
    row = []
    for key, data in CATEGORY_RULES.items():
        is_sub = key in categories
        prefix = "✅ " if is_sub else ""
        row.append(
            InlineKeyboardButton(
                text=f"{prefix}{data['label']}", callback_data=f"sub:{key}"
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="✔️ Готово", callback_data="sub:done")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_reply_markup(reply_markup=keyboard)


# === /salary — аналитика зарплат ===


@router.message(Command("salary"))
async def cmd_salary(message: types.Message):
    """Аналитика зарплат по категориям из hh.ru."""
    async with async_session() as session:
        job_service = JobService(session)
        jobs = await job_service.get_latest_jobs(limit=200)

    if not jobs:
        await message.answer("📊 Пока нет данных для аналитики.")
        return

    salary_data = {}
    salary_pattern = re.compile(r"(\d[\d\s]*\d)(?:\s*[-–]\s*(\d[\d\s]*\d))?")

    for job in jobs:
        if not job.description:
            continue
        matches = salary_pattern.findall(job.description)
        cat = job.category or "other"
        if cat not in salary_data:
            salary_data[cat] = []
        for match in matches:
            try:
                val1 = int(match[0].replace(" ", ""))
                if 10_000 <= val1 <= 1_000_000:
                    salary_data[cat].append(val1)
                if match[1]:
                    val2 = int(match[1].replace(" ", ""))
                    if 10_000 <= val2 <= 1_000_000:
                        salary_data[cat].append(val2)
            except (ValueError, IndexError):
                continue

    if not any(salary_data.values()):
        await message.answer(
            "📊 <b>Аналитика зарплат</b>\n\n"
            "Пока недостаточно данных с указанием зарплат.\n"
            "Подождите, пока соберётся больше вакансий с hh.ru.",
            parse_mode="HTML",
        )
        return

    response = "💰 <b>Аналитика зарплат</b>\n\n"
    for cat, salaries in sorted(
        salary_data.items(), key=lambda x: len(x[1]), reverse=True
    ):
        if not salaries:
            continue
        label = get_category_label(cat)
        avg = sum(salaries) // len(salaries)
        min_s = min(salaries)
        max_s = max(salaries)
        count = len(salaries)

        response += (
            f"{label}\n"
            f"  Средняя: <b>{avg:,}₽</b>\n"
            f"  Диапазон: {min_s:,} – {max_s:,}₽\n"
            f"  Выборка: {count} значений\n\n"
        )

    await message.answer(response, parse_mode="HTML")
