import os
import hashlib
import logging

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join("data", "cache", "audio")


def get_cache_path(text: str, voice_id: str) -> str:
    """Генерирует уникальный путь к файлу в кэше на основе текста и голоса."""
    # Создаем хэш от текста и ID голоса
    key = f"{text}_{voice_id}".encode("utf-8")
    file_hash = hashlib.md5(key).hexdigest()

    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR, exist_ok=True)

    return os.path.join(CACHE_DIR, f"{file_hash}.mp3")


def get_cached_audio(text: str, voice_id: str) -> bytes | None:
    """Возвращает байты аудио из кэша, если файл существует."""
    path = get_cache_path(text, voice_id)
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading from cache: {e}")
    return None


def save_to_cache(text: str, voice_id: str, audio_bytes: bytes):
    """Сохраняет байты аудио в кэш."""
    path = get_cache_path(text, voice_id)
    try:
        with open(path, "wb") as f:
            f.write(audio_bytes)
    except Exception as e:
        logger.error(f"Error saving to cache: {e}")
