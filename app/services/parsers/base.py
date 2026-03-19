import logging
import asyncio
import aiohttp
from abc import ABC, abstractmethod
from typing import List, Optional, Any
from ..job_service import JobService

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """
    Абстрактный базовый класс для всех парсеров вакансий.
    """

    def __init__(self):
        self.name = self.__class__.__name__

    def _get_proxy(self) -> Optional[str]:
        """Вспомогательный метод для получения прокси из менеджера."""
        from ...utils.proxy_manager import proxy_manager

        return proxy_manager.get_proxy()

    async def _request_with_retry(
        self, method: str, url: str, retries: int = 3, **kwargs
    ) -> Optional[Any]:
        """
        Выполняет HTTP-запрос с механизмом повторов при сетевых ошибках.
        Использует экспоненциальную задержку.
        """
        for i in range(retries):
            try:
                proxy = self._get_proxy()
                async with aiohttp.ClientSession() as session:
                    async with session.request(
                        method, url, proxy=proxy, timeout=20, **kwargs
                    ) as resp:
                        if resp.status in (403, 429):
                            raise Exception(
                                f"BLOCK: HTTP {resp.status} (Proxy: {proxy})"
                            )
                        if resp.status != 200:
                            raise Exception(
                                f"ERROR: HTTP {resp.status} (Proxy: {proxy})"
                            )
                        return await resp.json()
            except (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError) as e:
                wait_time = (i + 1) * 2
                if i < retries - 1:
                    logger.warning(
                        f"⚠️ {self.name} network error: {e}. Retrying... ({i + 1}/{retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise Exception(
                        f"NETWORK_FAILED after {retries} retries: {e} (Proxy: {proxy})"
                    )
            except Exception as e:
                raise e
        return None

    @abstractmethod
    async def parse(self, job_service: JobService) -> int:
        """
        Основной метод парсинга.
        Должен вернуть количество новых добавленных вакансий.
        """
        pass

    def get_name(self) -> str:
        return self.name


class ParserRegistry:
    """
    Реестр всех доступных парсеров.
    """

    _parsers: List[BaseParser] = []

    @classmethod
    def register(cls, parser: BaseParser):
        cls._parsers.append(parser)
        logger.info(f"✅ Parser registered: {parser.get_name()}")

    @classmethod
    def get_all_parsers(cls) -> List[BaseParser]:
        return cls._parsers


# Глобальный экземпляр реестра
registry = ParserRegistry()
