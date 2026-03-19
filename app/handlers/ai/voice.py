import os
import logging
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from ...services.voice_service import speech_to_text
from ..discovery.search import process_search

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.voice)
async def handle_voice(message: types.Message, state: FSMContext):
    """
    Обрабатывает голосовые сообщения: качает -> STT -> выполняет поиск или команду.
    """
    # 1. Отправляем статус "записывает аудио" (визуальный фидбек)
    logger.info(f"🎤 [VOICE] Received voice from user {message.from_user.id}")
    await message.bot.send_chat_action(message.chat.id, "typing")

    # 2. Получаем файл
    file_id = message.voice.file_id
    file = await message.bot.get_file(file_id)
    file_path = file.file_path
    logger.info(f"🎤 [VOICE] File path on TG servers: {file_path}")

    # 3. Скачиваем временно
    temp_path = f"temp_voice_{file_id}.ogg"
    logger.info(f"🎤 [VOICE] Downloading to {temp_path}...")
    await message.bot.download_file(file_path, temp_path)

    try:
        # 4. Транскрибируем
        logger.info("🎤 [VOICE] Sending to STT...")
        text = await speech_to_text(temp_path)
        logger.info(f"🎤 [VOICE] STT result: «{text}»")

        if not text:
            logger.warning(
                f"🎤 [VOICE] Empty text from STT for user {message.from_user.id}"
            )
            await message.reply(
                "🎙 Не удалось разобрать голос. Попробуйте сказать четче."
            )
            return

        await message.reply(f"🎙 <b>Вы сказали:</b>\n«{text}»", parse_mode="HTML")

        # 5. Логика обработки:
        # Если это похоже на команду
        if text.lower().startswith("старт") or text.lower() == "меню":
            from ..system.start import cmd_start  # UPDATED RELATIVE PATH

            await cmd_start(message)
        elif "профиль" in text.lower():
            from ..cabinet.profile import cmd_profile  # UPDATED RELATIVE PATH

            await cmd_profile(message)
        elif "категори" in text.lower() or "фильтр" in text.lower():
            from ..discovery.search import cmd_filter  # UPDATED RELATIVE PATH

            await cmd_filter(message)
        elif "горячие" in text.lower() or "свежие" in text.lower():
            from ..cabinet.profile import cmd_hot  # UPDATED RELATIVE PATH

            await cmd_hot(message)
        elif "резюме" in text.lower():
            from .resume import cmd_resume

            await cmd_resume(message, state)
        elif "вакансии" in text.lower() or "работу" in text.lower():
            from ..discovery.jobs import cmd_jobs  # UPDATED RELATIVE PATH

            await cmd_jobs(message)
        elif "поиск" in text.lower():
            from ..discovery.search import cmd_search  # UPDATED RELATIVE PATH

            await cmd_search(message, state)
        elif "интервью" in text.lower() or "собеседование" in text.lower():
            from .interview import cmd_interview

            await cmd_interview(message, state)
        elif "помощь" in text.lower() or "справка" in text.lower():
            from ..system.start import cmd_help  # UPDATED RELATIVE PATH

            await cmd_help(message)
        else:
            # По умолчанию считаем это поисковым запросом
            # Передаем текст напрямую, так как message.text заморожен
            await process_search(message, state, query_text=text)

    except Exception as e:
        logger.error(f"Voice handler error: {e}")
        await message.reply("❌ Произошла ошибка при обработке голоса.")
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.callback_query(F.data.startswith("tts:"))
async def handle_tts_callback(callback: types.CallbackQuery):
    """
    Озвучивает текст (вакансию или отчет).
    """
    from ...services.voice_service import text_to_speech

    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    target_type, target_id = parts[1:3]

    await callback.answer("🎙 Генерирую аудио...")

    text_to_read = ""

    if target_type == "job":
        from ...services.job_service import JobService
        from ...database import async_session

        async with async_session() as session:
            job_service = JobService(session)
            job = await job_service.get_job_by_id(int(target_id))
            if job:
                text_to_read = f"Вакансия: {job.title}. {job.description[:1000] if job.description else ''}"

    elif target_type == "market":
        # Заново получаем отчет (текст можно передать через state или просто взять из сообщения)
        text_to_read = callback.message.text

    if not text_to_read:
        await callback.message.answer("❌ Нечего озвучивать.")
        return

    # Получаем настройки голоса пользователя
    from ...services.user_service import UserService
    from ...database import async_session

    async with async_session() as session:
        user_service = UserService(session)
        user = await user_service.get_or_create_user(callback.from_user.id)
        user_voice = user.voice or "alloy"

    audio_file = await text_to_speech(text_to_read, voice=user_voice)
    if audio_file:
        await callback.message.answer_voice(audio_file)
    else:
        await callback.message.answer("❌ Ошибка при генерации голоса.")
