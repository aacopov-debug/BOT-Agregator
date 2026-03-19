import logging
import html
from datetime import datetime, timedelta, timezone
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Boolean
from sqlalchemy.sql import func
from sqlalchemy import select
from ...database import Base, async_session

logger = logging.getLogger(__name__)
router = Router()


class Reminder(Base):
    __tablename__ = "reminders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(BigInteger, nullable=False, index=True)
    text = Column(String(500), nullable=False)
    remind_at = Column(DateTime(timezone=True), nullable=False)
    job_id = Column(Integer, default=None)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReminderState(StatesGroup):
    waiting_text = State()
    waiting_time = State()


# ===== Быстрые напоминания из карточки вакансии =====


@router.callback_query(F.data.startswith("remind:"))
async def quick_remind(callback: types.CallbackQuery):
    """Быстрое напоминание из карточки вакансии."""
    job_id = int(callback.data.split(":")[1])

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏰ Через 1 час", callback_data=f"remset:1h:{job_id}"
                ),
                InlineKeyboardButton(
                    text="📅 Через 1 день", callback_data=f"remset:1d:{job_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📅 Через 3 дня", callback_data=f"remset:3d:{job_id}"
                ),
                InlineKeyboardButton(
                    text="📅 Через неделю", callback_data=f"remset:7d:{job_id}"
                ),
            ],
            [
                InlineKeyboardButton(text="◀️ Назад", callback_data=f"detail:{job_id}"),
            ],
        ]
    )

    await callback.message.edit_text(
        "⏰ <b>Установить напоминание</b>\n\n"
        "Когда вам напомнить об этой вакансии?\n\n"
        "💡 Используйте для:\n"
        "  • Follow-up после отклика\n"
        "  • Подготовка к собеседованию\n"
        "  • Проверить статус заявки",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remset:"))
async def set_quick_reminder(callback: types.CallbackQuery):
    """Установка быстрого напоминания."""
    parts = callback.data.split(":")
    interval = parts[1]
    job_id = int(parts[2])

    now = datetime.now(timezone.utc)
    delays = {
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1),
        "3d": timedelta(days=3),
        "7d": timedelta(days=7),
    }
    remind_at = now + delays.get(interval, timedelta(days=1))

    labels = {
        "1h": "через 1 час",
        "1d": "через 1 день",
        "3d": "через 3 дня",
        "7d": "через неделю",
    }

    from ...models.job import Job

    async with async_session() as session:
        job = (
            await session.execute(select(Job).where(Job.id == job_id))
        ).scalar_one_or_none()

        title = job.title if job else f"Вакансия #{job_id}"

        reminder = Reminder(
            user_telegram_id=callback.from_user.id,
            text=f"📋 {title}",
            remind_at=remind_at,
            job_id=job_id,
        )
        session.add(reminder)
        await session.commit()

    label = labels.get(interval, interval)
    time_str = remind_at.strftime("%d.%m в %H:%M")

    safe_title = html.escape(title)
    await callback.message.edit_text(
        f"✅ <b>Напоминание установлено!</b>\n\n"
        f"📋 {safe_title[:60]}\n"
        f"⏰ {label} ({time_str} UTC)\n\n"
        f"Бот пришлёт уведомление в указанное время.",
        parse_mode="HTML",
    )
    await callback.answer("⏰ Напоминание установлено!")


# ===== /remind — ручное напоминание =====


@router.message(Command("remind"))
async def cmd_remind(message: types.Message):
    """Показать активные напоминания."""
    async with async_session() as session:
        reminders = (
            (
                await session.execute(
                    select(Reminder)
                    .where(
                        Reminder.user_telegram_id == message.from_user.id,
                        Reminder.sent.is_(False),
                    )
                    .order_by(Reminder.remind_at)
                    .limit(10)
                )
            )
            .scalars()
            .all()
        )

    if not reminders:
        await message.answer(
            "⏰ <b>Напоминания</b>\n\n"
            "У вас нет активных напоминаний.\n\n"
            "💡 Установите через карточку вакансии\n"
            "(кнопка ⏰ Напомнить)",
            parse_mode="HTML",
        )
        return

    text = f"⏰ <b>Активные напоминания</b> ({len(reminders)})\n\n"
    buttons = []
    for r in reminders:
        time_str = r.remind_at.strftime("%d.%m %H:%M")
        safe_rem_text = html.escape(r.text[:50])
        text += f"📌 {safe_rem_text}\n   ⏰ {time_str} UTC\n\n"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"❌ {safe_rem_text[:25]}", callback_data=f"remdel:{r.id}"
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("remdel:"))
async def delete_reminder(callback: types.CallbackQuery):
    """Удалить напоминание."""
    rem_id = int(callback.data.split(":")[1])
    async with async_session() as session:
        rem = (
            await session.execute(
                select(Reminder).where(
                    Reminder.id == rem_id,
                    Reminder.user_telegram_id == callback.from_user.id,
                )
            )
        ).scalar_one_or_none()
        if rem:
            await session.delete(rem)
            await session.commit()

    await callback.answer("❌ Удалено")
    await cmd_remind(callback.message)


# ===== Фоновая задача — отправка напоминаний =====


async def send_reminders(bot):
    """Проверяет и отправляет напоминания. Вызывать каждую минуту."""
    now = datetime.now(timezone.utc)
    async with async_session() as session:
        due = (
            (
                await session.execute(
                    select(Reminder).where(
                        Reminder.sent.is_(False),
                        Reminder.remind_at <= now,
                    )
                )
            )
            .scalars()
            .all()
        )

        for rem in due:
            try:
                keyboard = None
                if rem.job_id:
                    keyboard = InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text="📋 Открыть вакансию",
                                    callback_data=f"detail:{rem.job_id}",
                                )
                            ]
                        ]
                    )

                safe_rem_text = html.escape(rem.text)
                await bot.send_message(
                    rem.user_telegram_id,
                    f"🔔 <b>Напоминание!</b>\n\n{safe_rem_text}",
                    parse_mode="HTML",
                    reply_markup=keyboard,
                )
                rem.sent = True
            except Exception as e:
                logger.error(f"Reminder send error: {e}")
                rem.sent = True

        await session.commit()
