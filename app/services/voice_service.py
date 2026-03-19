import aiohttp
import logging
import httpx
from openai import AsyncOpenAI
from aiogram.types import BufferedInputFile
from ..config import settings
from ..utils.proxy_manager import proxy_manager
from ..utils.audio_cache import get_cached_audio, save_to_cache

logger = logging.getLogger(__name__)


def get_openai_client():
    """Создает клиент OpenAI с поддержкой прокси, если они включены."""
    proxy = proxy_manager.get_proxy()
    # В httpx.AsyncClient аргумент называется 'proxy' (в единственном числе)
    http_client = httpx.AsyncClient(proxy=proxy) if proxy else None

    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY or settings.OPENROUTER_API_KEY,
        base_url="https://api.openai.com/v1"
        if settings.OPENAI_API_KEY
        else "https://openrouter.ai/api/v1",
        http_client=http_client,
    )


client = get_openai_client()


async def text_to_speech(text: str, voice: str = "nova") -> BufferedInputFile:
    """
    Конвертирует текст в речь (MP3) через OpenAI или ElevenLabs.
    """
    if voice.startswith("eleven_"):
        return await elevenlabs_tts(text, voice.replace("eleven_", ""))

    # Пытаемся взять из кэша
    cached = get_cached_audio(text, voice)
    if cached:
        return BufferedInputFile(cached, filename="voice_report.mp3")

    # Для OpenAI TTS также внедряем ротацию прокси, так как OpenAI блокирует РФ
    available_proxies = (
        settings.PROXY_LIST[:]
        if isinstance(settings.PROXY_LIST, list) and settings.USE_PROXIES
        else [None]
    )
    if not available_proxies:
        available_proxies = [None]

    import random

    random.shuffle(available_proxies)

    clean_text = text[:4000]
    max_retries = min(len(available_proxies), 3)

    for attempt in range(max_retries):
        proxy = available_proxies[attempt]
        try:
            # Создаем временный клиент с конкретным прокси
            http_client = httpx.AsyncClient(proxy=proxy) if proxy else None
            local_client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY or settings.OPENROUTER_API_KEY,
                base_url="https://api.openai.com/v1"
                if settings.OPENAI_API_KEY
                else "https://openrouter.ai/api/v1",
                http_client=http_client,
            )

            response = await local_client.audio.speech.create(
                model="tts-1-hd", voice=voice, input=clean_text
            )
            audio_bytes = await response.aread()

            # Сохраняем в кэш
            save_to_cache(text, voice, audio_bytes)
            return BufferedInputFile(audio_bytes, filename="voice_report.mp3")

        except Exception as e:
            logger.error(
                f"OpenAI TTS error with proxy {proxy} (attempt {attempt + 1}/{max_retries}): {e}"
            )
            if attempt == max_retries - 1:
                return None
    return None


async def elevenlabs_tts(text: str, voice_id: str) -> BufferedInputFile:
    """
    Конвертирует текст в речь через ElevenLabs API с обходом Cloudflare.
    Использует User-Agent и ротацию прокси при ошибках 403.
    """
    if not settings.ELEVENLABS_API_KEY:
        logger.error("ElevenLabs API key is missing!")
        return None

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": settings.ELEVENLABS_API_KEY,
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "DNT": "1",
        "Upgrade-Insecure-Requests": "1",
    }
    # Ограничение длины для экономии ElevenLabs
    clean_text = text[:1500]

    # Пытаемся взять из кэша
    cached = get_cached_audio(clean_text, voice_id)
    if cached:
        return BufferedInputFile(cached, filename="voice_report_premium.mp3")

    data = {
        "text": clean_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    # Пытаемся получить список всех доступных прокси для ротации
    available_proxies = (
        settings.PROXY_LIST[:]
        if isinstance(settings.PROXY_LIST, list) and settings.USE_PROXIES
        else [None]
    )
    if not available_proxies:
        available_proxies = [None]

    import random

    random.shuffle(available_proxies)

    max_retries = min(len(available_proxies), 3)
    for attempt in range(max_retries):
        proxy = available_proxies[attempt]
        try:
            timeout = aiohttp.ClientTimeout(total=40)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    url, json=data, headers=headers, proxy=proxy
                ) as response:
                    if response.status == 200:
                        audio_bytes = await response.read()
                        # Сохраняем в кэш
                        save_to_cache(clean_text, voice_id, audio_bytes)
                        return BufferedInputFile(
                            audio_bytes, filename="voice_report_premium.mp3"
                        )

                    err_text = await response.text()
                    if response.status == 403:
                        logger.warning(
                            f"ElevenLabs 403 (Cloudflare) with proxy {proxy}. Retrying... ({attempt + 1}/{max_retries})"
                        )
                        continue

                    logger.error(
                        f"ElevenLabs error ({response.status}): {err_text[:200]}"
                    )
                    return None
        except Exception as e:
            logger.error(f"ElevenLabs request failed with proxy {proxy}: {e}")
            if attempt == max_retries - 1:
                return None

    return None


async def speech_to_text(file_path: str) -> str:
    """
    Конвертирует аудиофайл в текст через OpenAI Whisper.
    """
    try:
        local_client = get_openai_client()
        logger.info(f"🎙 [STT] Using client with base_url: {local_client.base_url}")
        with open(file_path, "rb") as audio_file:
            transcription = await local_client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, response_format="text"
            )
        result = str(transcription).strip()
        logger.info(f"🎙 [STT] Transcription success: {result[:50]}...")
        return result
    except Exception as e:
        logger.error(f"🎙 [STT] Error during transcription: {e}", exc_info=True)
        return ""
