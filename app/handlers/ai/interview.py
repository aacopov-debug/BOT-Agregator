import logging
from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from ...services.interview_service import InterviewService
from ...services.user_service import UserService
from ...database import async_session
from ...utils.subscription import is_subscribed
from ...utils.keyboards import get_subscription_keyboard
from ...config import settings
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = Router()
interview_service = InterviewService()


class InterviewState(StatesGroup):
    waiting_for_context = State()
    interviewing = State()


async def _check_interview_access(user_id: int) -> tuple[bool, str]:
    """Проверяет, есть ли у пользователя доступ к интервью (премиум или кредиты)."""
    async with async_session() as session:
        us = UserService(session)
        user = await us.get_or_create_user(user_id)

        is_premium = (user.role == "admin") or (
            user.is_premium
            and user.premium_until
            and user.premium_until > datetime.now(timezone.utc)
        )
        if is_premium:
            return True, "<i>(Admin/Premium: безлимитный доступ)</i>\n\n"

        if user.ai_credits >= 5:
            user.ai_credits -= 5
            await session.commit()
            return True, f"<i>(Списано 5 кредитов, остаток: {user.ai_credits})</i>\n\n"

        return False, ""


@router.message(Command("interview"))
async def cmd_interview(message: types.Message, state: FSMContext):
    logger.info(f"🎯 [INTERVIEW] Command /interview from user {message.from_user.id}")
    await state.clear()

    # --- ПРОВЕРКА ПОДПИСКИ ---
    if settings.REQUIRED_CHANNEL_ID:
        subscribed = await is_subscribed(
            message.bot, message.from_user.id, settings.REQUIRED_CHANNEL_ID
        )
        if not subscribed:
            await message.answer(
                "🎤 <b>AI-тренажер интервью доступен только подписчикам!</b>\n\n"
                "Подпишитесь на наш канал, чтобы подготовиться к собеседованию на 100%.",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(
                    settings.REQUIRED_CHANNEL_LINK, "/interview"
                ),
            )
            return
    # -------------------------

    can_access, _ = await _check_interview_access(message.from_user.id)
    if not can_access:
        await message.answer(
            "❌ <b>Недостаточно кредитов</b>\n\n"
            "Для запуска AI-тренажера нужно 5 AI-кредитов.\n"
            "Пополните баланс в /balance или подключите /premium для безлимита!"
        )
        return

    await state.set_state(InterviewState.waiting_for_context)
    from ...utils.keyboards import CANCEL_KEYBOARD

    await message.answer(
        "🎤 <b>AI-Тренажер собеседований</b>\n\n"
        "Я проведу для вас имитацию реального интервью.\n"
        "Отправьте <b>описание вакансии</b> или ссылку на неё, чтобы я подготовил вопросы.\n\n"
        "Вы можете нажать кнопку ниже для отмены.",
        parse_mode="HTML",
        reply_markup=CANCEL_KEYBOARD,
    )


@router.callback_query(F.data == "finish_interview_now", StateFilter("*"))
async def interview_finish_early(callback: types.CallbackQuery, state: FSMContext):
    logger.info(
        f"🏁 [INTERVIEW] Finish early button triggered by user {callback.from_user.id}"
    )
    logger.info(f"🏁 [INTERVIEW] Finish early button from user {callback.from_user.id}")
    await callback.answer()
    data = await state.get_data()
    history = data.get("history", [])
    if not history:
        await state.clear()
        await callback.message.edit_text("❌ Интервью отменено.")
        return

    await callback.message.edit_text("⏳ <b>Завершаем досрочно.</b> Анализирую...")
    feedback = await interview_service.get_final_feedback(history=history)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 В главное меню", callback_data="menu:main")]
        ]
    )

    await callback.message.answer(feedback, parse_mode="HTML", reply_markup=kb)
    await state.clear()


@router.callback_query(F.data.startswith("interview:"))
async def cb_interview_start(callback: types.CallbackQuery, state: FSMContext):
    """Запуск интервью из карточки вакансии."""
    logger.info(f"🎯 [INTERVIEW] Callback start: {callback.data}")
    data_parts = callback.data.split(":")
    if len(data_parts) < 2 or data_parts[1] == "finish":
        logger.info("⏩ [INTERVIEW] Skipping 'finish' in start handler.")
        return  # Пропускаем если это кнопка завершения

    job_id = int(data_parts[1])
    logger.info(
        f"🎯 [INTERVIEW] Button interview for job {job_id} from user {callback.from_user.id}"
    )

    await state.clear()

    # --- ПРОВЕРКА ПОДПИСКИ ---
    if settings.REQUIRED_CHANNEL_ID:
        subscribed = await is_subscribed(
            callback.bot, callback.from_user.id, settings.REQUIRED_CHANNEL_ID
        )
        if not subscribed:
            await callback.message.answer(
                "🎤 <b>Для тренировки интервью нужно подписаться на канал!</b>\n\n"
                "Подпишитесь, чтобы разблокировать доступ к AI-тренажеру.",
                parse_mode="HTML",
                reply_markup=get_subscription_keyboard(
                    settings.REQUIRED_CHANNEL_LINK, callback.data
                ),
            )
            await callback.answer()
            return
    # -------------------------

    can_access, credit_text = await _check_interview_access(callback.from_user.id)
    if not can_access:
        await callback.answer("❌ Недостаточно кредитов (нужно 5)", show_alert=True)
        return

    from ...services.job_service import JobService

    async with async_session() as session:
        js = JobService(session)
        job = await js.get_job_by_id(job_id)

    if not job:
        await callback.answer("❌ Вакансия не найдена", show_alert=True)
        return

    job_desc = f"Вакансия: {job.title}\n\nОписание:\n{job.description or ''}"
    await state.update_data(job_desc=job_desc, history=[])
    await state.set_state(InterviewState.interviewing)

    await callback.message.answer(
        f"🤖 <b>Готов к интервью по вакансии:</b>\n"
        f"«{job.title}»\n\n"
        f"{credit_text}Начинаем. Расскажите немного о себе и вашем опыте.",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(InterviewState.waiting_for_context)
async def process_context(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Интервью отменено.")
        return

    # Кредиты уже списаны в cmd_interview
    await state.update_data(job_desc=message.text, history=[])
    await state.set_state(InterviewState.interviewing)
    await message.answer(
        "🤖 <b>Готов к интервью!</b>\nНачинаем. Расскажите немного о себе и вашем опыте."
    )


@router.message(InterviewState.interviewing)
async def process_interview_step(message: types.Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("❌ Интервью прекращено.")
        return

    data = await state.get_data()
    history = data.get("history", [])
    job_desc = data.get("job_desc", "")

    # Добавляем ответ пользователя
    history.append({"role": "user", "content": message.text})

    # Решаем, пора ли заканчивать (например, после 4-5 обменов)
    user_msgs_count = len(
        [m for m in history if m and isinstance(m, dict) and m.get("role") == "user"]
    )

    if user_msgs_count >= 5:
        await message.answer("⏳ <b>Интервью закончено.</b> Анализирую ваши ответы...")
        feedback = await interview_service.get_final_feedback(history)
        await message.answer(feedback, parse_mode="HTML")
        await state.clear()
    else:
        # Генерируем следующий вопрос
        await message.bot.send_chat_action(message.chat.id, "typing")
        question = await interview_service.get_next_question(
            history=history, job_desc=job_desc
        )
        history.append({"role": "assistant", "content": question})
        await state.update_data(history=history)

        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🏁 Завершить досрочно",
                        callback_data="finish_interview_now",
                    )
                ]
            ]
        )
        await message.answer(
            f"<b>Вопрос {user_msgs_count + 1}:</b>\n\n{question}",
            parse_mode="HTML",
            reply_markup=kb,
        )
