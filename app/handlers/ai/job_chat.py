import logging
import os
import html
from openai import AsyncOpenAI
from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from ...services.job_service import JobService
from ...services.user_service import UserService
from ...models.user import User
from ...database import async_session
from ...config import settings
from ...services.voice_service import speech_to_text

router = Router()
logger = logging.getLogger(__name__)

# Инициализируем клиент OpenAI
client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


class JobChatState(StatesGroup):
    chatting = State()


@router.callback_query(F.data.startswith("ask_ai:"))
async def start_job_chat(callback: types.CallbackQuery, state: FSMContext):
    """Начало диалога по вакансии."""
    job_id = int(callback.data.split(":")[1])

    if not settings.OPENAI_API_KEY:
        await callback.answer(
            "❌ AI недоступен (нет API-ключа OpenAI)", show_alert=True
        )
        return

    # Загружаем вакансию и пользователя из БД
    async with async_session() as session:
        job_service = JobService(session)
        job = await job_service.get_job_by_id(job_id)

        user_service = UserService(session)
        user = await user_service.get_or_create_user(
            callback.from_user.id, callback.from_user.username
        )

    if not job:
        await callback.answer("❌ Вакансия не найдена", show_alert=True)
        return

    is_prem = (user.role == "admin") or (
        user.is_premium
        and user.premium_until
        and user.premium_until > datetime.now(timezone.utc)
    )
    if user.ai_credits < 1 and not is_prem:
        await callback.answer(
            "❌ У вас закончились AI-кредиты.\nПополните баланс командой /balance",
            show_alert=True,
        )
        return

    await state.set_state(JobChatState.chatting)
    await state.update_data(
        job_id=job.id, job_title=job.title, job_text=f"{job.title}\n{job.description}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Завершить чат", callback_data="chat:end")]
        ]
    )

    await callback.message.answer(
        f"💬 <b>AI-помощник: {job.title}</b>\n\n"
        f"Задайте любой вопрос по этой вакансии! Например:\n"
        f"• <i>Какая здесь вилка ЗП?</i>\n"
        f"• <i>Можно ли работать полностью удаленно?</i>\n"
        f"• <i>Какой стек технологий требуется?</i>\n\n"
        f"Я прочитаю текст вакансии и постараюсь ответить.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )
    await callback.answer()


@router.message(JobChatState.chatting)
async def process_chat_message(
    message: types.Message, state: FSMContext, query_text: str = None
):
    """Обработка вопросов пользователя к AI."""
    # Используем переданный текст или текст из сообщения
    text = query_text or message.text

    if not text:
        return

    if message.text and message.text.startswith("/"):
        # Если введена любая команда (например /start, /cancel) - выходим из чата
        await state.clear()
        if message.text == "/cancel":
            await message.answer("💬 Диалог завершен.")
        return

    user_query = text  # Use the correct variable
    if not user_query:
        return

    data = await state.get_data()
    job_text = data.get("job_text", "")
    data.get("job_title", "Вакансия")

    # Сообщаем, что бот "печатает"
    await message.bot.send_chat_action(message.chat.id, "typing")

    # Формируем RAG-промпт
    prompt = (
        f"Ты — полезный AI-ассистент, помогающий кандидату разобраться с вакансией.\n\n"
        f"ТЕКСТ ВАКАНСИИ (Контекст):\n{job_text[:3000]}\n\n"
        f"ПОЛЬЗОВАТЕЛЬ СПРАШИВАЕТ: {user_query}\n\n"
        f"Ответь на вопрос кратко, вежливо и по существу, опираясь ТОЛЬКО на текст вакансии выше. "
        f"Если инфы нет, скажи, что в описании этого не указано. Без лишней воды."
    )

    response = await _call_rag_ai(prompt)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Завершить чат", callback_data="chat:end")]
        ]
    )

    if not response:
        await message.answer(
            "❌ Извините, не смог получить ответ от AI. Попробуйте еще раз.",
            reply_markup=keyboard,
        )
        return

    # Списываем 1 кредит за успешный ответ ИИ
    async with async_session() as session:
        from sqlalchemy import select

        user = (
            await session.execute(
                select(User).where(User.telegram_id == message.from_user.id)
            )
        ).scalar_one_or_none()
        if user:
            now = datetime.now(timezone.utc)
            is_prem = (user.role == "admin") or (
                user.is_premium and user.premium_until and user.premium_until > now
            )
            if not is_prem:
                user.ai_credits -= 1
            await session.commit()

    await message.reply(f"🤖 {response}", reply_markup=keyboard)


@router.message(JobChatState.chatting, F.voice)
async def process_chat_voice(message: types.Message, state: FSMContext):
    """Обработка голосовых вопросов к AI."""
    # 1. Визуальный фидбек
    await message.bot.send_chat_action(message.chat.id, "typing")

    # 2. Получаем и скачиваем файл
    file_id = message.voice.file_id
    file = await message.bot.get_file(file_id)
    temp_path = f"temp_voice_chat_{file_id}.ogg"
    await message.bot.download_file(file.file_path, temp_path)

    try:
        # 3. Транскрибируем
        text = await speech_to_text(temp_path)
        if not text:
            await message.reply(
                "🎙 Не удалось разобрать голос. Попробуйте сказать четче."
            )
            return

        await message.reply(
            f"🎙 <b>Вы спросили:</b>\n«{html.escape(text)}»", parse_mode="HTML"
        )

        # 4. Пробрасываем текст в основной обработчик напрямую
        await process_chat_message(message, state, query_text=text)

    except Exception as e:
        logger.error(f"Voice chat error: {e}")
        await message.reply("❌ Ошибка при обработке голоса.")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.callback_query(F.data == "chat:end")
async def end_chat(callback: types.CallbackQuery, state: FSMContext):
    """Кнопка для выхода из диалога."""
    current_state = await state.get_state()
    if current_state == JobChatState.chatting.state:
        await state.clear()

        data = await state.get_data()
        job_id = data.get("job_id")

        keyboard = None
        if job_id:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="📄 Вернуться к вакансии",
                            callback_data=f"detail:{job_id}",
                        )
                    ]
                ]
            )

        await callback.message.edit_text("💬 Диалог с AI завершен.")
        if keyboard:
            await callback.message.answer("Вы вышли из чата.", reply_markup=keyboard)
    else:
        # Если стейт уже сброшен
        await callback.message.delete()

    await callback.answer()


async def _call_rag_ai(prompt: str) -> str:
    """Вызов OpenAI (gpt-4o-mini) для быстрого ответа по контексту."""
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.5,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"RAG AI exception: {e}")
        return ""
