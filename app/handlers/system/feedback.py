"""Система отзывов и обратной связи."""

from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import Column, Integer, BigInteger, String, DateTime
from sqlalchemy.sql import func
from ...database import Base, async_session
from sqlalchemy import select

router = Router()


class Feedback(Base):
    __tablename__ = "feedbacks"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_telegram_id = Column(BigInteger, nullable=False)
    rating = Column(Integer, default=5)  # 1-5
    text = Column(String(1000), default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class FeedbackState(StatesGroup):
    waiting_text = State()


# ===== /feedback =====


@router.message(Command("feedback"))
async def cmd_feedback(message: types.Message):
    """Оценить бот."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐", callback_data="fb:rate:1"),
                InlineKeyboardButton(text="⭐⭐", callback_data="fb:rate:2"),
                InlineKeyboardButton(text="⭐⭐⭐", callback_data="fb:rate:3"),
                InlineKeyboardButton(text="⭐⭐⭐⭐", callback_data="fb:rate:4"),
                InlineKeyboardButton(text="⭐⭐⭐⭐⭐", callback_data="fb:rate:5"),
            ],
        ]
    )

    await message.answer(
        "📝 <b>Оценить бот</b>\n\n"
        "Выберите оценку от 1 до 5 ⭐\n\n"
        "Ваш отзыв поможет нам стать лучше!",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("fb:rate:"))
async def fb_select_rating(callback: types.CallbackQuery, state: FSMContext):
    rating = int(callback.data.split(":")[2])
    await state.update_data(rating=rating)

    stars = "⭐" * rating

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Пропустить", callback_data="fb:skip")],
        ]
    )

    from ...utils.keyboards import CANCEL_KEYBOARD

    await callback.message.edit_text(
        f"📝 Ваш рейтинг: {stars}\n\n"
        f"Напишите отзыв (необязательно):\n"
        f"Что нравится? Что улучшить?\n\n"
        f"Или нажмите «Пропустить».",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    # Поскольку edit_text заменяет inline клавиатуру, для reply клавиатуры (кнопка Отмена)
    # нужно отправить новое сообщение или дождаться следующего.
    # Но в aiogram ReplyKeyboardMarkup применяется к следующему ответу.
    # Для лучшего UX отправим подсказку с кнопкой.
    await callback.message.answer(
        "Вы можете нажать «Отмена» для возврата.", reply_markup=CANCEL_KEYBOARD
    )
    await state.set_state(FeedbackState.waiting_text)
    await callback.answer()


@router.callback_query(F.data == "fb:skip")
async def fb_skip_text(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    rating = data.get("rating", 5)

    async with async_session() as session:
        fb = Feedback(user_telegram_id=callback.from_user.id, rating=rating, text="")
        session.add(fb)
        await session.commit()

    stars = "⭐" * rating
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:start")]
        ]
    )
    await callback.message.edit_text(
        f"✅ <b>Спасибо за оценку!</b>\n\n"
        f"Ваш рейтинг: {stars}\n\n"
        f"💙 Мы ценим ваше мнение!",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await state.clear()
    await callback.answer("Спасибо!")


@router.message(FeedbackState.waiting_text)
async def fb_process_text(message: types.Message, state: FSMContext):
    data = await state.get_data()
    rating = data.get("rating", 5)
    text = message.text[:1000] if message.text else ""

    async with async_session() as session:
        fb = Feedback(user_telegram_id=message.from_user.id, rating=rating, text=text)
        session.add(fb)
        await session.commit()

    stars = "⭐" * rating
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:start")]
        ]
    )
    await message.answer(
        f"✅ <b>Спасибо за отзыв!</b>\n\n"
        f"Рейтинг: {stars}\n"
        f"📝 {text[:100]}{'...' if len(text) > 100 else ''}\n\n"
        f"💙 Ваше мнение очень важно!",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await state.clear()


# ===== Admin: просмотр отзывов =====


async def get_feedback_stats():
    """Статистика отзывов для admin-панели."""
    async with async_session() as session:
        from sqlalchemy import func as sqf

        total = (await session.execute(select(sqf.count(Feedback.id)))).scalar_one()

        avg = (await session.execute(select(sqf.avg(Feedback.rating)))).scalar_one()

        recent = (
            (
                await session.execute(
                    select(Feedback).order_by(Feedback.created_at.desc()).limit(5)
                )
            )
            .scalars()
            .all()
        )

    return {
        "total": total,
        "avg_rating": round(avg, 1) if avg else 0,
        "recent": recent,
    }
