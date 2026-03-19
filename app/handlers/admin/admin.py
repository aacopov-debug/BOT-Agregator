"""Admin-панель: полное управление ботом для администраторов."""

import logging
import os
from datetime import datetime, timedelta, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from sqlalchemy import select, func, delete
from ...services.job_service import JobService
from ...services.channel_rating import get_channel_ratings
from ...services.digest import get_trends, format_trends
from ...models.job import Job
from ...models.user import User
from ...models.favorite import Favorite
from ...database import async_session
from ...config import settings
from ...utils.categorizer import get_category_label

router = Router()
logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    """Проверка прав администратора через settings.ADMIN_ID."""
    return user_id == settings.ADMIN_ID


class AdminState(StatesGroup):
    waiting_for_channel = State()
    waiting_for_broadcast = State()
    waiting_for_remove_channel = State()


# ===== ГЛАВНОЕ МЕНЮ =====


@router.message(Command("admin"))
async def cmd_admin(message: types.Message, user_id: int = None):
    effective_user_id = user_id or message.from_user.id
    if not _is_admin(effective_user_id):
        await message.answer("🔒 Доступ запрещён.")
        return

    async with async_session() as session:
        job_service = JobService(session)
        total_jobs = await job_service.count_jobs()
        by_source = await job_service.count_by_source()
        by_category = await job_service.count_by_category()
        users_count = (await session.execute(select(func.count(User.id)))).scalar_one()
        fav_count = (
            await session.execute(select(func.count(Favorite.id)))
        ).scalar_one()

        # Активных за 24ч
        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        new_24h = (
            await session.execute(
                select(func.count(Job.id)).where(Job.created_at >= cutoff_24h)
            )
        ).scalar_one()

    channels = settings.CHANNELS_TO_PARSE
    ch_count = len(channels) if channels else 0

    response = (
        "🔐 <b>Admin Panel</b>\n\n"
        "━━━ <b>📊 Общая статистика</b> ━━━\n"
        f"  👥 Пользователей: <b>{users_count}</b>\n"
        f"  📋 Вакансий: <b>{total_jobs}</b>\n"
        f"  🆕 За 24ч: <b>+{new_24h}</b>\n"
        f"  ⭐ Избранных: <b>{fav_count}</b>\n"
        f"  📱 TG каналов: <b>{ch_count}</b>\n"
        f"  🏢 Источников: <b>{len(by_source)}</b>\n"
        f"  📂 Категорий: <b>{len(by_category)}</b>\n\n"
        "━━━ <b>По источникам</b> ━━━\n"
    )

    for src, count in sorted(by_source.items(), key=lambda x: x[1], reverse=True):
        if src == "hh.ru":
            name = "🏢 hh.ru"
        elif src == "habr.career":
            name = "💻 Habr"
        else:
            name = f"📱 @{src}"
        pct = round(count / total_jobs * 100) if total_jobs else 0
        response += f"  {name}: {count} ({pct}%)\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📱 Каналы", callback_data="adm:channels"),
                InlineKeyboardButton(text="👥 Пользователи", callback_data="adm:users"),
            ],
            [
                InlineKeyboardButton(
                    text="📂 Категории", callback_data="adm:categories"
                ),
                InlineKeyboardButton(text="📈 Тренды", callback_data="adm:trends"),
            ],
            [
                InlineKeyboardButton(text="📢 Рассылка", callback_data="adm:broadcast"),
                InlineKeyboardButton(text="🔄 Скрапинг", callback_data="adm:scrape"),
            ],
            [
                InlineKeyboardButton(text="🏆 Рейтинг", callback_data="adm:rating"),
                InlineKeyboardButton(text="⭐ Популярные", callback_data="adm:popular"),
            ],
            [
                InlineKeyboardButton(text="🗑 Очистка БД", callback_data="adm:cleanup"),
                InlineKeyboardButton(text="📊 Логи", callback_data="adm:log"),
            ],
            [
                InlineKeyboardButton(
                    text="📥 Экспорт БД", callback_data="adm:export_db"
                ),
                InlineKeyboardButton(text="🔧 Состояние", callback_data="adm:health"),
            ],
        ]
    )

    await message.answer(response, parse_mode="HTML", reply_markup=keyboard)


# ===== КАНАЛЫ =====


@router.callback_query(F.data == "adm:channels")
async def adm_channels(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    channels = settings.CHANNELS_TO_PARSE or []
    text = "📱 <b>Telegram-каналы</b>\n\n"
    for i, ch in enumerate(channels, 1):
        text += f"{i}. @{ch}\n"
    text += f"\nВсего: {len(channels)}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="➕ Добавить", callback_data="adm:add_channel"
                ),
                InlineKeyboardButton(
                    text="➖ Удалить", callback_data="adm:remove_channel"
                ),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:back")],
        ]
    )

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "adm:add_channel")
async def adm_add_channel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📱 Введите username канала (без @):\n"
        "<code>python_jobs</code>\n\n/cancel для отмены",
        parse_mode="HTML",
    )
    await state.set_state(AdminState.waiting_for_channel)
    await callback.answer()


@router.message(AdminState.waiting_for_channel)
async def process_add_channel(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("Отменено.")
        return

    channel = message.text.strip().replace("@", "").replace("https://t.me/", "")
    if not channel:
        await message.answer("Невалидное имя.")
    elif channel in (settings.CHANNELS_TO_PARSE or []):
        await message.answer(f"@{channel} уже в списке.")
    else:
        if settings.CHANNELS_TO_PARSE is None:
            settings.CHANNELS_TO_PARSE = []
        settings.CHANNELS_TO_PARSE.append(channel)
        await message.answer(
            f"✅ @{channel} добавлен!\nБудет обработан при следующем скрапинге."
        )
    await state.clear()


@router.callback_query(F.data == "adm:remove_channel")
async def adm_remove_channel(callback: types.CallbackQuery, state: FSMContext):
    channels = settings.CHANNELS_TO_PARSE or []
    if not channels:
        await callback.answer("Список каналов пуст")
        return

    text = "➖ Введите номер канала для удаления:\n\n"
    for i, ch in enumerate(channels, 1):
        text += f"{i}. @{ch}\n"
    text += "\n/cancel для отмены"

    await callback.message.answer(text)
    await state.set_state(AdminState.waiting_for_remove_channel)
    await callback.answer()


@router.message(AdminState.waiting_for_remove_channel)
async def process_remove_channel(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("Отменено.")
        return

    try:
        idx = int(message.text.strip()) - 1
        channels = settings.CHANNELS_TO_PARSE or []
        if 0 <= idx < len(channels):
            removed = channels.pop(idx)
            await message.answer(f"❌ @{removed} удалён из списка.")
        else:
            await message.answer("Неверный номер.")
    except ValueError:
        await message.answer("Введите номер.")
    await state.clear()


# ===== ПОЛЬЗОВАТЕЛИ =====


@router.callback_query(F.data == "adm:users")
async def adm_users(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).order_by(User.created_at.desc()).limit(20)
        )
        users = result.scalars().all()
        total = (await session.execute(select(func.count(User.id)))).scalar_one()

    text = f"👥 <b>Пользователи</b> ({total} всего)\n\n"
    for i, u in enumerate(users, 1):
        name = f"@{u.username}" if u.username else f"id:{u.telegram_id}"
        kw = (
            u.keywords[:25] + "…"
            if u.keywords and len(u.keywords) > 25
            else (u.keywords or "—")
        )
        date = u.created_at.strftime("%d.%m") if u.created_at else ""
        text += f"{i}. {name} — 🔑{kw} 📅{date}\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:back")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== КАТЕГОРИИ =====


@router.callback_query(F.data == "adm:categories")
async def adm_categories(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    async with async_session() as session:
        job_service = JobService(session)
        by_cat = await job_service.count_by_category()

    total = sum(by_cat.values()) or 1
    text = "📂 <b>Вакансии по категориям</b>\n\n"
    for cat, count in sorted(by_cat.items(), key=lambda x: x[1], reverse=True):
        label = get_category_label(cat)
        pct = round(count / total * 100)
        bar_len = int(pct / 10)
        bar = "▓" * bar_len + "░" * (10 - bar_len)
        text += f"{label}\n<code>{bar} {count} ({pct}%)</code>\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:back")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== ТРЕНДЫ =====


@router.callback_query(F.data == "adm:trends")
async def adm_trends(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    trends = await get_trends()
    text = format_trends(trends)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:back")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== РЕЙТИНГ ИСТОЧНИКОВ =====


@router.callback_query(F.data == "adm:rating")
async def adm_rating(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    from ...services.channel_rating import format_ratings

    ratings = await get_channel_ratings()
    text = format_ratings(ratings)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:back")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== ПОПУЛЯРНЫЕ ВАКАНСИИ =====


@router.callback_query(F.data == "adm:popular")
async def adm_popular(callback: types.CallbackQuery):
    """Вакансии с наибольшим количеством ⭐."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    async with async_session() as session:
        stmt = (
            select(Job, func.count(Favorite.id).label("fav_count"))
            .join(Favorite, Favorite.job_id == Job.id)
            .group_by(Job.id)
            .order_by(func.count(Favorite.id).desc())
            .limit(10)
        )
        result = await session.execute(stmt)
        rows = result.all()

    if not rows:
        text = "⭐ Пока никто ничего не добавил в избранное."
    else:
        text = "⭐ <b>Популярные вакансии</b>\n\n"
        for i, (job, count) in enumerate(rows, 1):
            stars = "⭐" * min(count, 5)
            text += f"<b>{i}.</b> {stars} ({count}x)\n   {job.title[:55]}\n\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:back")]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== РАССЫЛКА =====


@router.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    await callback.message.answer(
        "📢 <b>Рассылка</b>\n\n"
        "Введите текст (поддерживается HTML):\n"
        "<code>&lt;b&gt;жирный&lt;/b&gt;</code>\n\n/cancel для отмены",
        parse_mode="HTML",
    )
    await state.set_state(AdminState.waiting_for_broadcast)
    await callback.answer()


@router.message(AdminState.waiting_for_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("Отменено.")
        return

    text = message.text
    async with async_session() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    sent, failed = 0, 0
    for user in users:
        try:
            await message.bot.send_message(user.telegram_id, text, parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        f"📢 <b>Рассылка завершена</b>\n\n"
        f"✅ Доставлено: {sent}\n❌ Ошибок: {failed}\n📊 Всего: {len(users)}",
        parse_mode="HTML",
    )
    await state.clear()


# ===== СКРАПИНГ =====


@router.callback_query(F.data == "adm:scrape")
async def adm_scrape(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    await callback.message.answer("🔄 Запускаю скрапинг всех источников...")
    await callback.answer()

    from ...services.scraper import run_scraper
    from ...services.hh_parser import run_hh_scraper
    from ...services.habr_parser import run_habr_scraper
    from ...services.kwork_parser import run_kwork_scraper
    from ...services.fl_parser import run_fl_scraper
    from ...services.superjob_parser import run_superjob_scraper

    tg = await run_scraper(
        settings.CHANNELS_TO_PARSE if settings.CHANNELS_TO_PARSE else None
    )
    hh = await run_hh_scraper()
    habr = await run_habr_scraper()
    kwork = await run_kwork_scraper()
    fl = await run_fl_scraper()
    sj = await run_superjob_scraper()

    await callback.message.answer(
        f"✅ <b>Скрапинг завершён!</b>\n\n"
        f"📱 Telegram: +{tg}\n"
        f"🏢 hh.ru: +{hh}\n"
        f"💻 Habr: +{habr}\n"
        f"🟠 Kwork: +{kwork}\n"
        f"🔵 FL.ru: +{fl}\n"
        f"🟣 SuperJob: +{sj}\n\n"
        f"📦 Итого: <b>+{tg + hh + habr + kwork + fl + sj}</b>",
        parse_mode="HTML",
    )


# ===== ОЧИСТКА =====


@router.callback_query(F.data == "adm:cleanup")
async def adm_cleanup(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 3 дня", callback_data="adm:clean3"),
                InlineKeyboardButton(text="🗑 7 дней", callback_data="adm:clean7"),
                InlineKeyboardButton(text="🗑 30 дней", callback_data="adm:clean30"),
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="adm:back")],
        ]
    )
    await callback.message.edit_text(
        "🗑 <b>Очистка БД</b>\n\nУдалить вакансии старше:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("adm:clean"))
async def adm_do_cleanup(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    days = int(callback.data.replace("adm:clean", ""))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    async with async_session() as session:
        stmt = delete(Job).where(Job.created_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()

    await callback.message.edit_text(
        f"🗑 Удалено <b>{result.rowcount}</b> вакансий старше {days} дней.",
        parse_mode="HTML",
    )
    await callback.answer()


# ===== ЛОГИ =====


@router.callback_query(F.data == "adm:log")
async def adm_log(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    try:
        with open("bot.log", "r", encoding="utf-8") as f:
            lines = f.readlines()
        last_lines = lines[-20:]
        text = "📊 <b>Последние 20 строк лога:</b>\n\n<code>"
        text += "".join(line[:80] + "\n" for line in last_lines)
        text += "</code>"
    except FileNotFoundError:
        text = "📊 Лог-файл не найден."

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📥 Скачать лог", callback_data="adm:download_log"
                ),
                InlineKeyboardButton(text="◀️ Назад", callback_data="adm:back"),
            ]
        ]
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "adm:download_log")
async def adm_download_log(callback: types.CallbackQuery):
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    try:
        with open("bot.log", "rb") as f:
            content = f.read()
        doc = BufferedInputFile(content, filename="bot.log")
        await callback.message.answer_document(doc, caption="📊 Полный лог-файл")
    except FileNotFoundError:
        await callback.message.answer("Лог-файл не найден.")
    await callback.answer()


# ===== ЭКСПОРТ БД =====


@router.callback_query(F.data == "adm:export_db")
async def adm_export_db(callback: types.CallbackQuery):
    """Экспорт всех вакансий в CSV."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return

    async with async_session() as session:
        result = await session.execute(
            select(Job).order_by(Job.created_at.desc()).limit(1000)
        )
        jobs = result.scalars().all()

    if not jobs:
        await callback.message.answer("БД пуста.")
        await callback.answer()
        return

    csv = "id,title,source,category,link,created_at\n"
    for j in jobs:
        title = j.title.replace('"', '""')[:100]
        date = j.created_at.strftime("%Y-%m-%d %H:%M") if j.created_at else ""
        csv += f'{j.id},"{title}",{j.source},{j.category},{j.link or ""},{date}\n'

    doc = BufferedInputFile(csv.encode("utf-8"), filename="jobs_export.csv")
    await callback.message.answer_document(
        doc, caption=f"📥 Экспорт: {len(jobs)} вакансий"
    )
    await callback.answer()


# ===== СОСТОЯНИЕ =====


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: types.Message):
    if not _is_admin(message.from_user.id):
        await message.answer("🔒 Доступ запрещён.")
        return
    await _show_health(message, edit=False)


@router.callback_query(F.data == "adm:health")
async def adm_health(callback: types.CallbackQuery):
    """Состояние системы."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒")
        return
    await _show_health(callback.message, edit=True)
    await callback.answer()


async def _show_health(message: types.Message, edit: bool):
    import platform
    import sys

    try:
        import psutil

        process = psutil.Process(os.getpid())
        ram_mb = process.memory_info().rss / 1024 / 1024
        cpu_percent = process.cpu_percent(interval=0.1)
        sys_ram = psutil.virtual_memory().percent
        psutil_info = (
            f"💽 ОЗУ (Бот): <code>{ram_mb:.1f} MB</code>\n"
            f"💻 CPU (Бот): <code>{cpu_percent}%</code>\n"
            f"🖥 ОЗУ (Система): <code>{sys_ram}%</code>\n"
        )
    except ImportError:
        psutil_info = "💽 ОЗУ: <code>(psutil не установлен)</code>\n"

    # Размер БД
    db_size = "—"
    if os.path.exists("jobs.db"):
        size_bytes = os.path.getsize("jobs.db")
        if size_bytes > 1_000_000:
            db_size = f"{size_bytes / 1_000_000:.1f} MB"
        else:
            db_size = f"{size_bytes / 1_000:.0f} KB"

    # Размер лога
    log_size = "—"
    if os.path.exists("bot.log"):
        size_bytes = os.path.getsize("bot.log")
        log_size = f"{size_bytes / 1_000:.0f} KB"

    # Статистика парсеров
    from sqlalchemy import select
    from app.database import async_session
    from app.models.stats import ParserStats

    parsers_summary = "—"
    try:
        async with async_session() as session:
            stmt = select(ParserStats)
            res = await session.execute(stmt)
            all_stats = res.scalars().all()
            if all_stats:
                ok = sum(1 for s in all_stats if s.status == "OK")
                errors = sum(1 for s in all_stats if s.status != "OK")
                parsers_summary = f"🟢 {ok} | 🔴 {errors}"
    except Exception:
        pass

    text = (
        "🔧 <b>Состояние системы</b>\n\n"
        f"🐍 Python: <code>{sys.version.split()[0]}</code>\n"
        f"💻 OS: <code>{platform.system()} {platform.release()}</code>\n"
        f"{psutil_info}"
        f"🗄 БД: <code>{db_size}</code>\n"
        f"📊 Лог: <code>{log_size}</code>\n"
        f"🤖 Парсеры: <code>{parsers_summary}</code>\n"
        f"📱 Каналов: <code>{len(settings.CHANNELS_TO_PARSE or [])}</code>\n"
        f"⏱ Интервал: <code>{settings.PARSE_INTERVAL_SECONDS}с</code>\n"
        f"🕐 Время: <code>{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}</code>\n"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Статистика парсеров", callback_data="adm:parser_stats"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🌐 Открыть Web-Дашборд", url="http://127.0.0.1:8085/dashboard"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="adm:back")],
        ]
    )

    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ===== НАВИГАЦИЯ =====


@router.callback_query(F.data == "adm:back")
async def adm_back(callback: types.CallbackQuery):
    await callback.answer()
    await cmd_admin(callback.message, user_id=callback.from_user.id)


# ===== МОДЕРАЦИЯ (HR-ПАНЕЛЬ) =====


@router.callback_query(F.data.startswith("mod_ok:"))
async def mod_hr_ok(callback: types.CallbackQuery):
    """Одобрить платную вакансию от HR."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒", show_alert=True)
        return

    job_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        job = await session.get(Job, job_id)
        if not job:
            await callback.answer("Вакансия не найдена.", show_alert=True)
            return

        job.moderation_status = "approved"
        employer_id = job.employer_id
        await session.commit()

    await callback.message.edit_text(
        callback.message.html_text + "\n\n<b>✅ ОДОБРЕНО</b>"
    )
    await callback.answer("Вакансия одобрена и попала в выдачу!")

    # Уведомляем HR
    try:
        await callback.message.bot.send_message(
            employer_id,
            f"✅ <b>Отличные новости!</b>\n\n"
            f"Ваша вакансия «{job.title}» успешно прошла модерацию и теперь доступна кандидатам в агрегаторе.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить HR {employer_id}: {e}")


@router.callback_query(F.data.startswith("mod_fail:"))
async def mod_hr_fail(callback: types.CallbackQuery):
    """Отклонить платную вакансию от HR."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("🔒", show_alert=True)
        return

    job_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        job = await session.get(Job, job_id)
        if not job:
            await callback.answer("Вакансия не найдена.", show_alert=True)
            return

        job.moderation_status = "rejected"
        employer_id = job.employer_id
        await session.commit()

    await callback.message.edit_text(
        callback.message.html_text + "\n\n<b>❌ ОТКЛОНЕНО</b>"
    )
    await callback.answer("Вакансия отклонена.")

    # Уведомляем HR
    try:
        await callback.message.bot.send_message(
            employer_id,
            f"❌ <b>Модерация отклонена</b>\n\n"
            f"Ваша вакансия «{job.title}» не прошла проверку администратором. "
            f"Если вы считаете, что произошла ошибка, свяжитесь с поддержкой.",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Не удалось уведомить HR {employer_id}: {e}")
