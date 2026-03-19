import html
from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select, func, update, delete
from ...models.application import Application
from ...models.job import Job
from ...database import async_session
from ...utils.categorizer import get_category_label

router = Router()

# ===== Стадии CRM-пайплайна =====
STAGES = ["applied", "viewed", "interview", "offer", "rejected"]

STATUS_LABELS = {
    "applied": "📤 Отправлено",
    "viewed": "👁 Просмотрено",
    "interview": "🗓 Собеседование",
    "offer": "🎉 Оффер",
    "rejected": "❌ Отказ",
}

STATUS_EMOJI = {
    "applied": "📤",
    "viewed": "👁",
    "interview": "🗓",
    "offer": "🎉",
    "rejected": "❌",
}


class NoteState(StatesGroup):
    waiting_for_note = State()


def _pipeline_bar(current_status: str) -> str:
    """Визуальный пайплайн: ● — текущий, ○ — будущий, ● — пройденный."""
    stages_flow = ["applied", "viewed", "interview", "offer"]
    # rejected — особый случай (может произойти на любом этапе)
    if current_status == "rejected":
        return "📤 → 👁 → 🗓 → ❌ Отказ"

    parts = []
    passed = True
    for stage in stages_flow:
        emoji = STATUS_EMOJI[stage]
        if stage == current_status:
            parts.append(f"[{emoji}]")
            passed = False
        elif passed:
            parts.append(emoji)
        else:
            parts.append("○")

    return " → ".join(parts)


# ===== Кнопка «Откликнуться» — сохранение в трекер =====


@router.callback_query(F.data.startswith("apply:"))
async def apply_to_job(callback: types.CallbackQuery):
    """Добавляет вакансию в трекер откликов."""
    job_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    async with async_session() as session:
        existing = await session.execute(
            select(Application).where(
                Application.user_telegram_id == user_id, Application.job_id == job_id
            )
        )
        if existing.scalar_one_or_none():
            await callback.answer("📤 Уже в трекере!")
            return

        job = (
            await session.execute(select(Job).where(Job.id == job_id))
        ).scalar_one_or_none()
        if not job:
            await callback.answer("Вакансия не найдена")
            return

        app = Application(user_telegram_id=user_id, job_id=job_id, status="applied")
        session.add(app)
        await session.commit()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Мои отклики", callback_data="tracker:list")],
        ]
    )

    safe_title = html.escape(job.title)
    await callback.message.answer(
        f"📤 <b>Отклик сохранён!</b>\n\n"
        f"<b>{safe_title}</b>\n"
        f"Статус: 📤 Отправлено\n\n"
        f"Отслеживайте через /applications",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer("✅ Добавлено в трекер!")


# ===== /applications — Список откликов =====


@router.message(Command("applications"))
async def cmd_applications(message: types.Message):
    await _show_applications(message, message.from_user.id)


@router.callback_query(F.data == "tracker:list", StateFilter("*"))
async def tracker_list(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    await _show_applications(callback.message, callback.from_user.id, edit=True)


async def _show_applications(message, user_id, edit=False):
    async with async_session() as session:
        stmt = (
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(Application.user_telegram_id == user_id)
            .order_by(Application.updated_at.desc())
            .limit(15)
        )
        result = await session.execute(stmt)
        rows = result.all()

        stats_stmt = (
            select(Application.status, func.count(Application.id))
            .where(Application.user_telegram_id == user_id)
            .group_by(Application.status)
        )
        stats = dict((await session.execute(stats_stmt)).all())

    total = sum(stats.values())
    if total == 0:
        text = (
            "📋 <b>Мини-CRM: Трекер откликов</b>\n\n"
            "Пока пусто! Нажмите 📤 Быстрый отклик на любой вакансии."
        )
        if edit:
            await message.edit_text(text, parse_mode="HTML")
        else:
            await message.answer(text, parse_mode="HTML")
        return

    # Шапка со статистикой по стадиям
    text = f"📋 <b>Мини-CRM: Мои отклики</b> ({total})\n\n"
    for status in STAGES:
        count = stats.get(status, 0)
        if count:
            text += f"  {STATUS_LABELS[status]}: <b>{count}</b>\n"
    text += "\n━━━━━━━━━━━━━━━━━━━━\n\n"

    # Список откликов с пайплайном
    for app, job in rows:
        emoji = STATUS_EMOJI.get(app.status, "📤")
        now = datetime.now(timezone.utc)
        days_ago = (now - app.created_at).days if app.created_at else 0
        time_str = f"{days_ago}д назад" if days_ago > 0 else "сегодня"

        safe_title = html.escape(job.title[:50])
        text += f"{emoji} <b>{safe_title}</b>\n   {job.source} • {time_str}"
        if app.note:
            safe_note = html.escape(app.note[:25])
            text += f" • 📝 <i>{safe_note}...</i>"
        text += "\n\n"

    # Кнопки — карточки (первые 5)
    buttons = []
    for app, job in rows[:5]:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{STATUS_EMOJI.get(app.status, '📤')} {job.title[:30]}",
                    callback_data=f"tracker:detail:{app.id}",
                )
            ]
        )

    # Фильтры по стадиям
    filter_row = []
    for status in STAGES:
        count = stats.get(status, 0)
        if count:
            filter_row.append(
                InlineKeyboardButton(
                    text=f"{STATUS_EMOJI[status]} {count}",
                    callback_data=f"tracker:filter:{status}",
                )
            )
    if filter_row:
        buttons.append(filter_row)

    buttons.append(
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="tracker:list")]
    )
    buttons.append(
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")]
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    if edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


# ===== Фильтр по стадии =====


@router.callback_query(F.data.startswith("tracker:filter:"))
async def tracker_filter(callback: types.CallbackQuery):
    status_filter = callback.data.split(":")[2]
    user_id = callback.from_user.id

    async with async_session() as session:
        stmt = (
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.user_telegram_id == user_id,
                Application.status == status_filter,
            )
            .order_by(Application.updated_at.desc())
            .limit(10)
        )
        result = await session.execute(stmt)
        rows = result.all()

    label = STATUS_LABELS.get(status_filter, status_filter)
    text = f"📋 <b>Фильтр: {label}</b> ({len(rows)})\n\n"

    for app, job in rows:
        now = datetime.now(timezone.utc)
        days_ago = (now - app.created_at).days if app.created_at else 0
        time_str = f"{days_ago}д назад" if days_ago > 0 else "сегодня"
        safe_title = html.escape(job.title[:50])
        text += f"• <b>{safe_title}</b> — {time_str}\n"

    buttons = []
    for app, job in rows[:5]:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"📄 {job.title[:30]}",
                    callback_data=f"tracker:detail:{app.id}",
                )
            ]
        )
    buttons.append(
        [InlineKeyboardButton(text="◀️ Все отклики", callback_data="tracker:list")]
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()


# ===== Детали отклика (CRM карточка) =====


@router.callback_query(F.data.startswith("tracker:detail:"), StateFilter("*"))
async def tracker_detail(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    if state:
        await state.clear()
    app_id = int(callback.data.split(":")[2])

    async with async_session() as session:
        stmt = (
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(Application.id == app_id)
        )
        result = await session.execute(stmt)
        row = result.one_or_none()

    if not row:
        await callback.answer("Не найдено")
        return

    app, job = row
    label = STATUS_LABELS.get(app.status, app.status)
    cat = get_category_label(job.category) if job.category else ""
    date_created = app.created_at.strftime("%d.%m.%Y %H:%M") if app.created_at else "—"

    # Дата смены статуса
    date_status = ""
    if hasattr(app, "status_changed_at") and app.status_changed_at:
        date_status = app.status_changed_at.strftime("%d.%m.%Y %H:%M")
    elif app.updated_at:
        date_status = app.updated_at.strftime("%d.%m.%Y %H:%M")

    # Визуальный пайплайн
    pipeline = _pipeline_bar(app.status)

    safe_title = html.escape(job.title)
    text = (
        f"📋 <b>CRM-Карточка отклика</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>{safe_title}</b>\n"
        f"📍 {job.source} • {cat}\n\n"
        f"<b>Стадия:</b> {label}\n"
        f"{pipeline}\n\n"
        f"📅 Отклик: {date_created}\n"
        f"🔄 Обновлено: {date_status}\n"
    )

    if app.note:
        safe_note = html.escape(app.note)
        text += f"\n📝 <b>Заметка:</b>\n<i>{safe_note}</i>\n"

    if job.link:
        text += f"\n🔗 <a href='{job.link}'>Открыть вакансию</a>"

    # Кнопки: стадии пайплайна (кроме текущей)
    stage_buttons = []
    for status in STAGES:
        if status != app.status:
            stage_buttons.append(
                InlineKeyboardButton(
                    text=STATUS_LABELS[status],
                    callback_data=f"tracker:set:{app.id}:{status}",
                )
            )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            stage_buttons[:2],
            stage_buttons[2:4] if len(stage_buttons) > 2 else [],
            [
                InlineKeyboardButton(
                    text="📝 Заметка", callback_data=f"tracker:note:{app.id}"
                ),
                InlineKeyboardButton(
                    text="📄 Вакансия", callback_data=f"detail:{app.job_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"tracker:del:{app.id}"
                ),
                InlineKeyboardButton(text="◀️ Назад", callback_data="tracker:list"),
            ],
        ]
    )
    keyboard.inline_keyboard = [row for row in keyboard.inline_keyboard if row]

    await callback.message.edit_text(
        text, parse_mode="HTML", disable_web_page_preview=True, reply_markup=keyboard
    )
    await callback.answer()


# ===== Смена статуса =====


@router.callback_query(F.data.startswith("tracker:set:"))
async def tracker_set_status(callback: types.CallbackQuery):
    parts = callback.data.split(":")
    app_id = int(parts[2])
    new_status = parts[3]

    async with async_session() as session:
        stmt = (
            update(Application)
            .where(
                Application.id == app_id,
                Application.user_telegram_id == callback.from_user.id,
            )
            .values(status=new_status, status_changed_at=datetime.now(timezone.utc))
        )
        await session.execute(stmt)
        await session.commit()

    label = STATUS_LABELS.get(new_status, new_status)
    await callback.answer(f"✅ Статус: {label}")

    # Обновляем CRM-карточку
    callback.data = f"tracker:detail:{app_id}"
    await tracker_detail(callback)


# ===== Добавление заметки (FSM) =====


@router.callback_query(F.data.startswith("tracker:note:"))
async def tracker_add_note(callback: types.CallbackQuery, state: FSMContext):
    app_id = int(callback.data.split(":")[2])

    # Загружаем текущую заметку
    async with async_session() as session:
        stmt = select(Application).where(Application.id == app_id)
        app = (await session.execute(stmt)).scalar_one_or_none()

    safe_current = html.escape(app.note) if app and app.note else "пусто"

    await state.set_state(NoteState.waiting_for_note)
    await state.update_data(app_id=app_id)

    await callback.message.edit_text(
        f"📝 <b>Заметка к отклику</b>\n\n"
        f"Текущая заметка: <i>{safe_current}</i>\n\n"
        f"Введите новую заметку (до 500 символов)\n"
        f"или /cancel для отмены:",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(NoteState.waiting_for_note)
async def process_note(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("Отменено. Используйте /applications для возврата.")
        return

    data = await state.get_data()
    app_id = data.get("app_id")
    note_text = (message.text or "")[:500]

    async with async_session() as session:
        stmt = (
            update(Application)
            .where(
                Application.id == app_id,
                Application.user_telegram_id == message.from_user.id,
            )
            .values(note=note_text)
        )
        await session.execute(stmt)
        await session.commit()

    await state.clear()

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 К отклику", callback_data=f"tracker:detail:{app_id}"
                )
            ],
            [InlineKeyboardButton(text="📋 Все отклики", callback_data="tracker:list")],
        ]
    )

    safe_note_preview = html.escape(note_text[:100])
    await message.answer(
        f"✅ Заметка сохранена!\n\n📝 <i>{safe_note_preview}...</i>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# ===== Удаление отклика =====


@router.callback_query(F.data.startswith("tracker:del:"))
async def tracker_delete(callback: types.CallbackQuery):
    app_id = int(callback.data.split(":")[2])

    async with async_session() as session:
        stmt = delete(Application).where(
            Application.id == app_id,
            Application.user_telegram_id == callback.from_user.id,
        )
        await session.execute(stmt)
        await session.commit()

    await callback.answer("🗑 Удалено")
    await _show_applications(callback.message, callback.from_user.id, edit=True)
