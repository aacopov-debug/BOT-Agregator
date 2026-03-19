import logging
from telethon import TelegramClient
from ...config import settings
from ..job_service import JobService
from .base import BaseParser, registry

logger = logging.getLogger(__name__)


class TelegramParser(BaseParser):
    def __init__(self):
        super().__init__()
        # Имя сессии должно совпадать с тем, что в auth_user.py
        self.client = TelegramClient("user_session", settings.API_ID, settings.API_HASH)
        self.keywords = [
            "вакансия",
            "job",
            "hiring",
            "ищем",
            "remote",
            "удаленка",
            "работа",
            "требуется",
            "оклад",
            "зарплата",
            "developer",
            "разработчик",
        ]

    async def parse(self, job_service: JobService) -> int:
        if not settings.CHANNELS_TO_PARSE:
            logger.warning("No channels configured for parsing")
            return 0

        total_new = 0
        try:
            # Используем существующий сеанс (созданный через auth_user.py)
            if not self.client.is_connected():
                await self.client.connect()

            if not await self.client.is_user_authorized():
                logger.error(
                    "Telegram User Session: NOT AUTHORIZED. Please run 'python auth_user.py' first."
                )
                return 0

            logger.info("Telethon client started (User Session auth)")

            for channel_username in settings.CHANNELS_TO_PARSE:
                try:
                    logger.info(f"Parsing channel: {channel_username}")
                    async for message in self.client.iter_messages(
                        channel_username, limit=20
                    ):
                        if not message.text:
                            continue

                        if any(kw in message.text.lower() for kw in self.keywords):
                            lines = message.text.split("\n")
                            title = lines[0][:255] if lines else "Без названия"
                            link = f"https://t.me/{channel_username}/{message.id}"

                            job = await job_service.add_job(
                                title=title,
                                description=message.text,
                                link=link,
                                source=channel_username,
                            )
                            if job:
                                total_new += 1
                except Exception as e:
                    logger.error(f"Error parsing channel {channel_username}: {e}")

        except Exception as e:
            logger.error(f"Telegram parser main error: {e}")

        return total_new


# Регистрация парсера
registry.register(TelegramParser())
