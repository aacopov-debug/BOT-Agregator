from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from ...database import async_session  # UPDATED RELATIVE PATH
from ...models.user import User  # UPDATED RELATIVE PATH

router = Router()


class BroadcastState(StatesGroup):
    waiting_for_message = State()


@router.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message, state: FSMContext):
    """Рассылка сообщения всем пользователям (только для админов)."""
    from .admin import _is_admin

    if not _is_admin(message.from_user.id):
        await message.answer("⚠️ Нет прав.")
        return

    await message.answer(
        "📢 <b>Режим рассылки</b>\n\n"
        "Отправьте мне сообщение, которое получат ВСЕ пользователи бота.\n"
        "Можно использовать форматирование (жирный, курсив и т.д.).\n\n"
        "/cancel для отмены.",
        parse_mode="HTML",
    )
    await state.set_state(BroadcastState.waiting_for_message)


@router.message(BroadcastState.waiting_for_message)
async def process_broadcast(message: types.Message, state: FSMContext):
    if message.text and message.text.startswith("/"):
        await state.clear()
        await message.answer("Рассылка отменена.")
        return

    # Сохраняем тип сообщения и ID для пересылки
    msg_type = "text"
    file_id = None

    if message.photo:
        msg_type = "photo"
        file_id = message.photo[-1].file_id
    elif message.video:
        msg_type = "video"
        file_id = message.video.file_id
    elif message.document:
        msg_type = "document"
        file_id = message.document.file_id

    await state.update_data(
        msg_id=message.message_id,
        from_chat_id=message.chat.id,
        msg_type=msg_type,
        file_id=file_id,
        caption=message.caption or message.text,
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отправить всем", callback_data="broadcast:confirm"
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast:cancel")],
        ]
    )

    await message.answer(
        "📝 <b>Предпросмотр вашей рассылки:</b>\n━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )

    # Показываем админу, что получится
    if msg_type == "text":
        await message.answer(message.text, parse_mode=message.html_text and "HTML")
    elif msg_type == "photo":
        await message.answer_photo(file_id, caption=message.caption, parse_mode="HTML")
    elif msg_type == "video":
        await message.answer_video(file_id, caption=message.caption, parse_mode="HTML")
    else:
        await message.bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )

    await message.answer(
        "━━━━━━━━━━━━━━━━━━━━\nОтправляем всем пользователям?",
        reply_markup=keyboard,
        parse_mode="HTML",
    )


@router.callback_query(F.data == "broadcast:confirm")
async def confirm_broadcast(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg_id = data.get("msg_id")
    from_chat_id = data.get("from_chat_id")
    data.get("msg_type")

    async with async_session() as session:
        users = (await session.execute(select(User.telegram_id))).scalars().all()

    await callback.message.edit_text(
        f"⏳ Рассылка запущена для {len(users)} пользователей..."
    )

    success = 0
    failed = 0

    import asyncio

    for user_id in users:
        try:
            # Используем copy_message для сохранения типа и форматирования
            await callback.bot.copy_message(
                chat_id=user_id, from_chat_id=from_chat_id, message_id=msg_id
            )
            success += 1
            if success % 20 == 0:
                await asyncio.sleep(0.5)  # Пауза каждые 20 сообщений
            else:
                await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    await callback.message.answer(
        f"📢 <b>Рассылка завершена!</b>\n\n"
        f"✅ Доставлено: <b>{success}</b>\n"
        f"❌ Не доставлено: <b>{failed}</b>",
        parse_mode="HTML",
    )
    await state.clear()


@router.callback_query(F.data == "broadcast:cancel")
async def cancel_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.answer()
