"""Избранное с пагинацией, удалением и подтверждением очистки."""

from aiogram import Router, types, F
import html
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from ...services.job_service import JobService
from ...database import async_session
from ...utils.categorizer import get_category_label

router = Router()
FAV_PER_PAGE = 5


@router.message(Command("favorites"))
async def cmd_favorites(message: types.Message):
    """Показать избранные вакансии с пагинацией."""
    await _show_favorites_page(message, page=0)


async def _show_favorites_page(message_or_callback, page: int):
    """Отображает страницу избранного."""
    is_callback = isinstance(message_or_callback, types.CallbackQuery)
    user_id = message_or_callback.from_user.id

    async with async_session() as session:
        job_service = JobService(session)
        all_favs = await job_service.get_favorites(user_id)

    total = len(all_favs)
    if total == 0:
        text = (
            "⭐ <b>Избранное пусто</b>\n\n"
            "Нажимайте ⭐ при просмотре вакансий через /jobs\n"
            "или кнопку «📋 Вакансии»."
        )
        if is_callback:
            await message_or_callback.message.edit_text(text, parse_mode="HTML")
            await message_or_callback.answer()
        else:
            await message_or_callback.answer(text, parse_mode="HTML")
        return

    total_pages = max(1, (total + FAV_PER_PAGE - 1) // FAV_PER_PAGE)
    page = min(page, total_pages - 1)
    start = page * FAV_PER_PAGE
    end = start + FAV_PER_PAGE
    page_jobs = all_favs[start:end]

    response = f"⭐ <b>Избранное</b> ({total})  •  Стр. {page + 1}/{total_pages}\n\n"
    for i, job in enumerate(page_jobs, start=start + 1):
        cat_label = get_category_label(job.category) if job.category else ""
        safe_title = html.escape(job.title[:70])
        link_text = f"<a href='{job.link}'>→</a>" if job.link else ""
        response += f"<b>{i}.</b> {cat_label} {safe_title}\n   {link_text}\n\n"

    rows = []
    # Кнопки удаления для каждой вакансии
    for job in page_jobs:
        short = job.title[:18] + "…" if len(job.title) > 18 else job.title
        rows.append(
            [
                InlineKeyboardButton(text="📄", callback_data=f"detail:{job.id}"),
                InlineKeyboardButton(text="📝", callback_data=f"fav:note:{job.id}"),
                InlineKeyboardButton(
                    text=f"❌ {short}", callback_data=f"fav:del:{job.id}:{page}"
                ),
            ]
        )

    # Навигация
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"fav_page:{page - 1}"))
    nav.append(
        InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
    )
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"fav_page:{page + 1}"))
    rows.append(nav)

    # Кнопка очистки
    rows.append(
        [InlineKeyboardButton(text="🗑 Очистить всё", callback_data="fav:confirm_clear")]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    if is_callback:
        await message_or_callback.message.edit_text(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(
            response,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )


@router.callback_query(F.data.startswith("fav_page:"))
async def callback_fav_page(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    await _show_favorites_page(callback, page)


@router.callback_query(F.data.startswith("fav:add:"))
async def callback_fav_add(callback: types.CallbackQuery):
    """Добавить в избранное."""
    job_id = int(callback.data.split(":")[2])
    async with async_session() as session:
        job_service = JobService(session)
        added = await job_service.add_favorite(callback.from_user.id, job_id)
        count = await job_service.count_favorites(callback.from_user.id)
    if added:
        await callback.answer(f"⭐ Добавлено! (всего: {count})")
    else:
        await callback.answer("Уже в избранном")


@router.callback_query(F.data.startswith("fav:del:"))
async def callback_fav_remove(callback: types.CallbackQuery):
    """Удалить из избранного и обновить список."""
    parts = callback.data.split(":")
    job_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 else 0

    async with async_session() as session:
        job_service = JobService(session)
        await job_service.remove_favorite(callback.from_user.id, job_id)

    await callback.answer("❌ Удалено")
    await _show_favorites_page(callback, page)


@router.callback_query(F.data == "fav:confirm_clear")
async def callback_confirm_clear(callback: types.CallbackQuery):
    """Подтверждение очистки."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Да, очистить", callback_data="fav:clear_yes"
                ),
                InlineKeyboardButton(text="❌ Отмена", callback_data="fav:clear_no"),
            ]
        ]
    )
    await callback.message.edit_text(
        "⚠️ <b>Удалить ВСЕ вакансии из избранного?</b>\n\nЭто действие нельзя отменить.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data == "fav:clear_yes")
async def callback_fav_clear(callback: types.CallbackQuery):
    """Batch-очистка избранного (один SQL запрос)."""
    async with async_session() as session:
        job_service = JobService(session)
        await job_service.clear_all_favorites(callback.from_user.id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔍 Поиск вакансий", callback_data="menu:search_btn"
                )
            ],
            [InlineKeyboardButton(text="👤 Профиль", callback_data="profile:main")],
        ]
    )
    await callback.message.edit_text("⭐ Избранное очищено.", reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "fav:clear_no")
async def callback_fav_cancel(callback: types.CallbackQuery):
    await callback.answer("Отменено")
    await _show_favorites_page(callback, 0)


# ===== Заметки к избранному =====


@router.callback_query(F.data.startswith("fav:note:"))
async def fav_add_note(callback: types.CallbackQuery, state: FSMContext):
    """Запрос текста заметки."""

    job_id = int(callback.data.split(":")[2])

    await state.update_data(note_job_id=job_id)

    await callback.message.answer(
        "📝 <b>Добавить заметку</b>\n\n"
        "Напишите заметку к вакансии:\n"
        "Например: «Отправил CV 10.03», «Ждать ответа»\n\n"
        "/cancel для отмены",
        parse_mode="HTML",
    )

    from .states import NoteState

    await state.set_state(NoteState.waiting_note)
    await callback.answer()
